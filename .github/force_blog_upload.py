#!/usr/bin/env python3
"""Force-upload blog hub files over explicit FTPS and prove they landed."""

from __future__ import annotations

import ftplib
import io
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SERVER = os.environ["FTP_SERVER"]
USER = os.environ["FTP_USERNAME"]
PASSWORD = os.environ["FTP_PASSWORD"]
ROOT = Path.cwd()
SLUG = re.search(
    r'slug:\s*"([^"]+)"',
    (ROOT / "js" / "blog-data.js").read_text(encoding="utf-8"),
).group(1)
TOKEN = os.environ.get("GITHUB_SHA", "local")[:12]
MARKER_NAME = "deploy-marker.txt"
SITE = "https://www.mansaodolago.com"


def connect() -> ftplib.FTP:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    errors: list[str] = []
    ftp = ftplib.FTP_TLS(context=ctx, timeout=60)
    try:
        ftp.connect(SERVER, 21)
        ftp.login(USER, PASSWORD)
        ftp.prot_p()
        ftp.set_pasv(True)
        print(f"Connected explicit FTPS pwd={ftp.pwd()}")
        return ftp
    except Exception as exc:
        errors.append(f"port21:{exc}")
        try:
            ftp.close()
        except Exception:
            pass
    raise SystemExit("FTPS login failed: " + " | ".join(errors))


def listing(ftp: ftplib.FTP) -> list[str]:
    try:
        return ftp.nlst()
    except ftplib.error_perm:
        return []


def try_cwd(ftp: ftplib.FTP, path: str) -> bool:
    try:
        ftp.cwd(path)
        return True
    except ftplib.error_perm:
        return False


def find_web_roots(ftp: ftplib.FTP) -> list[str]:
    home = ftp.pwd()
    found: list[str] = []
    names = set(listing(ftp))
    if "blog" in names or "index.html" in names:
        found.append(home)
    for rel in (
        "public_html",
        "www",
        "domains/mansaodolago.com/public_html",
        "mansaodolago.com/public_html",
    ):
        ftp.cwd(home)
        ok = True
        for part in rel.split("/"):
            if not try_cwd(ftp, part):
                ok = False
                break
        if ok:
            names = set(listing(ftp))
            if "blog" in names or "index.html" in names:
                found.append(ftp.pwd())
    ftp.cwd(home)
    # de-dupe, keep order
    out: list[str] = []
    for item in found:
        if item not in out:
            out.append(item)
    if not out:
        out.append(home)
    print("Candidate web roots:", out)
    return out


def ensure_dir(ftp: ftplib.FTP, name: str) -> None:
    if name not in set(listing(ftp)):
        try:
            ftp.mkd(name)
        except ftplib.error_perm as exc:
            print(f"mkdir {name} note: {exc}")
    ftp.cwd(name)


def stor(ftp: ftplib.FTP, local: Path, remote_name: str) -> None:
    with local.open("rb") as handle:
        ftp.storbinary(f"STOR {remote_name}", handle)
    print(f"put {local.as_posix()} -> {ftp.pwd()}/{remote_name}")


def retr(ftp: ftplib.FTP, remote_name: str) -> bytes:
    buf = io.BytesIO()
    ftp.retrbinary(f"RETR {remote_name}", buf.write)
    return buf.getvalue()


def upload_into(ftp: ftplib.FTP, web_root: str) -> None:
    if not try_cwd(ftp, web_root):
        raise RuntimeError(f"cannot cwd {web_root}")
    ensure_dir(ftp, "blog")
    for html in sorted((ROOT / "blog").glob("*.html")):
        stor(ftp, html, html.name)
    ftp.cwd(web_root)
    ensure_dir(ftp, "js")
    stor(ftp, ROOT / "js" / "blog-data.js", "blog-data.js")
    stor(ftp, ROOT / "js" / "blog.js", "blog.js")
    ftp.cwd(web_root)
    stor(ftp, ROOT / "sitemap.xml", "sitemap.xml")
    stor(ftp, ROOT / ".htaccess", ".htaccess")
    marker = io.BytesIO(f"{TOKEN} {SLUG}\n".encode("utf-8"))
    ftp.cwd(web_root)
    ftp.cwd("blog")
    ftp.storbinary(f"STOR {MARKER_NAME}", marker)
    print(f"put marker {TOKEN} {SLUG}")


def ftp_proves_slug(ftp: ftplib.FTP, web_root: str) -> None:
    ftp.cwd(web_root)
    ftp.cwd("blog")
    hub = retr(ftp, "index.html").decode("utf-8", "replace")
    if SLUG not in hub:
        raise SystemExit(f"Remote {web_root}/blog/index.html missing {SLUG}")
    ftp.cwd(web_root)
    ftp.cwd("js")
    data = retr(ftp, "blog-data.js").decode("utf-8", "replace")
    if SLUG not in data:
        raise SystemExit(f"Remote {web_root}/js/blog-data.js missing {SLUG}")
    print(f"FTP read-back OK at {web_root}")


def http_has(url: str, needle: str) -> bool:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "mdl-force-blog/1.0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        print(f"HTTP {url} error: {exc}")
        return False
    ok = needle in body
    print(f"HTTP {url} -> {'hit' if ok else 'miss'}")
    return ok


def main() -> int:
    print(f"Newest slug: {SLUG}")
    ftp = connect()
    roots = find_web_roots(ftp)
    last_error = None
    for web_root in roots:
        try:
            print(f"Uploading into {web_root}")
            upload_into(ftp, web_root)
            ftp_proves_slug(ftp, web_root)
        except Exception as exc:
            last_error = exc
            print(f"Upload/verify failed at {web_root}: {exc}")
            continue
        time.sleep(4)
        if http_has(f"{SITE}/blog/{MARKER_NAME}", TOKEN):
            if not http_has(f"{SITE}/blog/", SLUG):
                print(
                    "::warning::Marker is live but /blog/ HTML still old. "
                    "Cloudflare or LiteSpeed may be serving a cached hub."
                )
            print(f"Live web root confirmed: {web_root}")
            ftp.quit()
            return 0
        print(f"{web_root} accepted FTP but is not the public site")
    ftp.quit()
    if last_error:
        print(last_error)
    raise SystemExit(
        "Uploaded over FTP but https://www.mansaodolago.com/blog/"
        f"{MARKER_NAME} never showed the token. Check FTP home vs public_html."
    )


if __name__ == "__main__":
    sys.exit(main())
