#!/usr/bin/env python
"""Download YCB object model archives from the official YCB S3 mirror."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


OBJECTS_URL = "https://ycb-benchmarks.s3.amazonaws.com/data/objects.json"
BASE_URL = "http://ycb-benchmarks.s3-website-us-east-1.amazonaws.com/data/"
DEFAULT_FILE_TYPES = ("google_16k", "berkeley_processed")


def _fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _archive_url(object_id: str, file_type: str) -> str:
    if file_type in ("berkeley_rgbd", "berkeley_rgb_highres"):
        return f"{BASE_URL}berkeley/{object_id}/{object_id}_{file_type}.tgz"
    if file_type == "berkeley_processed":
        return f"{BASE_URL}berkeley/{object_id}/{object_id}_berkeley_meshes.tgz"
    return f"{BASE_URL}google/{object_id}_{file_type}.tgz"


def _head_ok(url: str) -> tuple[bool, int | None]:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            length = response.headers.get("Content-Length")
            return True, int(length) if length else None
    except urllib.error.HTTPError as exc:
        if exc.code == 405:
            return True, None
        return False, None
    except Exception:
        return False, None


def _download(url: str, archive_path: Path, expected_bytes: int | None, retries: int) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists() and expected_bytes and archive_path.stat().st_size == expected_bytes:
        return
    tmp = archive_path.with_suffix(archive_path.suffix + ".part")
    curl = shutil.which("curl")
    if curl:
        cmd = [
            curl,
            "-L",
            "--fail",
            "--retry",
            str(retries),
            "--retry-delay",
            "2",
            "--connect-timeout",
            "30",
            "--speed-time",
            "60",
            "--speed-limit",
            "1024",
            "-o",
            str(tmp),
            url,
        ]
        subprocess.run(cmd, check=True)
        if expected_bytes and tmp.stat().st_size != expected_bytes:
            raise IOError(f"downloaded {tmp.stat().st_size} bytes, expected {expected_bytes}")
        tmp.replace(archive_path)
        return
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as response, tmp.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
            if expected_bytes and tmp.stat().st_size != expected_bytes:
                raise IOError(f"downloaded {tmp.stat().st_size} bytes, expected {expected_bytes}")
            tmp.replace(archive_path)
            return
        except Exception:
            if attempt == retries:
                raise
            time.sleep(min(30, 2**attempt))


def _safe_extract(archive_path: Path, output_dir: Path) -> None:
    output_root = output_dir.resolve()
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            target = (output_dir / member.name).resolve()
            if not str(target).startswith(str(output_root)):
                raise RuntimeError(f"Refusing unsafe tar member: {member.name}")
        archive.extractall(output_dir)


def _download_one(
    object_id: str,
    file_type: str,
    output_dir: Path,
    extract: bool,
    keep_archives: bool,
    retries: int,
) -> dict[str, Any]:
    url = _archive_url(object_id, file_type)
    ok, expected_bytes = _head_ok(url)
    if not ok:
        return {"object_id": object_id, "file_type": file_type, "status": "missing", "url": url}
    archive_path = output_dir / "archives" / f"{object_id}_{file_type}.tgz"
    _download(url, archive_path, expected_bytes, retries)
    extracted = False
    if extract:
        _safe_extract(archive_path, output_dir)
        extracted = True
        if not keep_archives:
            archive_path.unlink(missing_ok=True)
    return {
        "object_id": object_id,
        "file_type": file_type,
        "status": "downloaded",
        "url": url,
        "archive": str(archive_path),
        "bytes": expected_bytes,
        "extracted": extracted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("scene_lab/assets/raw/ycb/object_models"),
        help="Output directory for extracted YCB object models.",
    )
    parser.add_argument("--objects", nargs="*", help="Object ids to download. Defaults to all official objects.")
    parser.add_argument(
        "--repo",
        help="Optional Hugging Face dataset repo, e.g. ai-habitat/ycb. When set, download the full snapshot instead of official S3 tgz files.",
    )
    parser.add_argument("--file-types", nargs="+", default=list(DEFAULT_FILE_TYPES))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--no-extract", action="store_true")
    parser.add_argument("--keep-archives", action="store_true")
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    output_dir = args.out.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.repo:
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise SystemExit(
                "huggingface_hub is required for --repo downloads. "
                "Install with: python -m pip install huggingface_hub"
            ) from exc
        snapshot_path = snapshot_download(
            repo_id=args.repo,
            repo_type="dataset",
            local_dir=str(output_dir),
            resume_download=True,
        )
        files = [path for path in output_dir.rglob("*") if path.is_file()]
        summary = {
            "repo": args.repo,
            "output_dir": str(output_dir),
            "snapshot_path": str(snapshot_path),
            "file_count": len(files),
            "bytes": sum(path.stat().st_size for path in files),
        }
        summary_path = args.summary or output_dir / "ycb_download_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(summary_path)
        print(json.dumps(summary, indent=2))
        return

    objects = args.objects or _fetch_json(OBJECTS_URL)["objects"]
    jobs = [(object_id, file_type) for object_id in objects for file_type in args.file_types]
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [
            pool.submit(
                _download_one,
                object_id,
                file_type,
                output_dir,
                not args.no_extract,
                args.keep_archives,
                args.retries,
            )
            for object_id, file_type in jobs
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            print(f"[{index}/{len(jobs)}] {result['object_id']} {result['file_type']} {result['status']}", flush=True)

    summary = {
        "objects_url": OBJECTS_URL,
        "output_dir": str(output_dir),
        "object_count": len(objects),
        "file_types": args.file_types,
        "downloaded": sum(item["status"] == "downloaded" for item in results),
        "missing": sum(item["status"] == "missing" for item in results),
        "results": sorted(results, key=lambda item: (item["object_id"], item["file_type"])),
    }
    summary_path = args.summary or output_dir / "ycb_download_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(summary_path)
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    main()
