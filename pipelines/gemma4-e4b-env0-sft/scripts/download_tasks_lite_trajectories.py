#!/usr/bin/env python3
"""Download env-0 tasks-lite trajectory artifacts from Hugging Face."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_DATASET = "benchflow/env0-experiment-trajectories"
DEFAULT_PREFIX = "tasks-lite-gpt55-xhigh"
DEFAULT_WAVES = ("wave1", "wave2", "wave3", "wave4")
FILES = ("acp_trajectory.jsonl", "result.json", "meta.json")


def parse_env_file(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip("\"'")
    return env


def hf_token(env: dict[str, str]) -> str | None:
    return env.get("HF_TOKEN") or env.get("HUGGING_FACE_TOKEN")


def headers(token: str | None) -> dict[str, str]:
    out = {"Accept": "application/json", "User-Agent": "env0-gemma4-sft"}
    if token:
        out["Authorization"] = f"Bearer {token}"
    return out


def request_json_with_headers(url: str, token: str | None) -> tuple[Any, dict[str, str]]:
    req = urllib.request.Request(url, headers=headers(token))
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
        return payload, dict(resp.headers.items())


def next_link(headers_: dict[str, str]) -> str | None:
    link = headers_.get("Link") or headers_.get("link")
    if not link:
        return None
    for part in link.split(","):
        section = part.strip()
        if 'rel="next"' not in section:
            continue
        start = section.find("<")
        end = section.find(">", start + 1)
        if start != -1 and end != -1:
            return section[start + 1 : end]
    return None


def list_tree(dataset: str, revision: str, path: str, token: str | None) -> list[dict[str, Any]]:
    encoded_path = urllib.parse.quote(path.strip("/"), safe="/")
    url: str | None = (
        f"https://huggingface.co/api/datasets/{dataset}/tree/{revision}/{encoded_path}"
        "?recursive=false&expand=false&limit=1000"
    )
    items: list[dict[str, Any]] = []
    while url:
        payload, response_headers = request_json_with_headers(url, token)
        if not isinstance(payload, list):
            raise SystemExit(f"Unexpected Hugging Face tree payload for {path}: {type(payload).__name__}")
        items.extend(payload)
        url = next_link(response_headers)
    return items


def download_file(dataset: str, revision: str, remote_path: str, local_path: Path, token: str | None, force: bool) -> None:
    if local_path.exists() and not force:
        return
    encoded_path = urllib.parse.quote(remote_path.strip("/"), safe="/")
    url = f"https://huggingface.co/datasets/{dataset}/resolve/{revision}/{encoded_path}"
    req = urllib.request.Request(url, headers=headers(token))
    local_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return
        raise
    tmp = local_path.with_suffix(local_path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(local_path)


def trajectory_dirs(dataset: str, revision: str, prefix: str, subset: str, waves: list[str], token: str | None) -> list[tuple[str, str]]:
    dirs: list[tuple[str, str]] = []
    for wave in waves:
        if subset == "reward1":
            root = f"{prefix}/{wave}/trajectories"
        elif subset == "all":
            root = f"{prefix}/all/{wave}"
        else:
            raise SystemExit(f"Unsupported subset: {subset}")
        for item in list_tree(dataset, revision, root, token):
            if item.get("type") != "directory":
                continue
            path = str(item["path"])
            name = path.rsplit("/", 1)[-1]
            dirs.append((wave, name))
    return dirs


def remote_dir(prefix: str, subset: str, wave: str, name: str) -> str:
    if subset == "reward1":
        return f"{prefix}/{wave}/trajectories/{name}"
    return f"{prefix}/all/{wave}/{name}"


def download_one(args: tuple[str, str, argparse.Namespace, str | None]) -> dict[str, Any]:
    wave, name, ns, token = args
    src_dir = remote_dir(ns.prefix, ns.subset, wave, name)
    dst_dir = ns.out / wave / name
    downloaded = []
    for filename in FILES:
        local_path = dst_dir / filename
        download_file(ns.dataset, ns.revision, f"{src_dir}/{filename}", local_path, token, ns.force)
        if local_path.exists():
            downloaded.append(filename)
    return {"wave": wave, "name": name, "files": downloaded}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--revision", default="main")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--subset", choices=["reward1", "all"], default="reward1")
    parser.add_argument("--waves", default=",".join(DEFAULT_WAVES))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--max-workers", type=int, default=24)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    env = parse_env_file(args.env_file)
    env.update(os.environ)
    token = hf_token(env)
    waves = [wave.strip() for wave in args.waves.split(",") if wave.strip()]
    dirs = trajectory_dirs(args.dataset, args.revision, args.prefix, args.subset, waves, token)
    if args.limit is not None:
        dirs = dirs[: args.limit]

    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(args.max_workers, 1)) as pool:
        futures = [pool.submit(download_one, (wave, name, args, token)) for wave, name in dirs]
        for future in concurrent.futures.as_completed(futures):
            rows.append(future.result())

    complete = sum(1 for row in rows if set(FILES).issubset(set(row["files"])))
    manifest = {
        "dataset": args.dataset,
        "revision": args.revision,
        "prefix": args.prefix,
        "subset": args.subset,
        "waves": waves,
        "requested": len(dirs),
        "complete": complete,
        "out": str(args.out),
        "items": sorted(rows, key=lambda row: (row["wave"], row["name"])),
    }
    (args.out / "download_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("requested", "complete", "out")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
