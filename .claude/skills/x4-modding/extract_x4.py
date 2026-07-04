#!/usr/bin/env python3
"""Extract files from X4 Foundations .cat/.dat archives (no XRCatTool needed).

The game ships data as NN.cat (a text index: "<path> <size> <timestamp> <sha1>")
plus NN.dat (all those files concatenated in order). A file's bytes start at the
cumulative sum of the sizes before it in its .cat. Higher-numbered cats override
lower ones (DLC/patches), so we keep the last occurrence of each path.

Usage:
  py extract_x4.py libraries/god.xml libraries/gamestarts.xml md/gs_boso.xml
  py extract_x4.py --list headquarters          # print index paths containing a substring
  py extract_x4.py --out ./dump maps/XU_ep2_universe/galaxy.xml
  X4_DIR="D:/path/to/X4 Foundations" py extract_x4.py ...   # override game dir

Paths are the in-archive virtual paths (forward slashes), case-insensitive.
"""
import os, sys, glob, argparse

DEFAULT_X4 = r"E:\steam\steamapps\common\X4 Foundations"


def build_index(x4):
    index = {}
    for cat in sorted(glob.glob(os.path.join(x4, "*.cat"))):
        if cat.lower().endswith("_sig.cat"):
            continue
        dat = cat[:-4] + ".dat"
        if not os.path.exists(dat):
            continue
        off = 0
        with open(cat, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip("\r\n")
                if not line:
                    continue
                parts = line.rsplit(" ", 3)  # path may contain spaces; size/ts/hash are last 3
                if len(parts) < 4:
                    continue
                path, size = parts[0], parts[1]
                try:
                    size = int(size)
                except ValueError:
                    continue
                index[path.replace("\\", "/").lower()] = (dat, off, size)
                off += size
    return index


def main():
    ap = argparse.ArgumentParser(description="Extract files from X4 .cat/.dat archives")
    ap.add_argument("paths", nargs="*", help="in-archive virtual paths to extract")
    ap.add_argument("--out", default=".", help="output directory (default: cwd)")
    ap.add_argument("--x4", default=os.environ.get("X4_DIR", DEFAULT_X4), help="X4 install dir")
    ap.add_argument("--list", metavar="SUBSTR", help="list index paths containing SUBSTR, then exit")
    args = ap.parse_args()

    if not os.path.isdir(args.x4):
        sys.exit(f"X4 dir not found: {args.x4} (set X4_DIR or --x4)")
    index = build_index(args.x4)

    if args.list is not None:
        for k in sorted(index):
            if args.list.lower() in k:
                print(k)
        return

    if not args.paths:
        ap.print_help()
        return

    os.makedirs(args.out, exist_ok=True)
    for t in args.paths:
        key = t.replace("\\", "/").lower()
        hit = index.get(key)
        if not hit:
            base = key.rsplit("/", 1)[-1]
            cands = [k for k in index if k.endswith("/" + base)][:10]
            print(f"NOT FOUND {t}; did you mean: {cands}")
            continue
        dat, off, size = hit
        with open(dat, "rb") as f:
            f.seek(off)
            data = f.read(size)
        outp = os.path.join(args.out, os.path.basename(t))
        with open(outp, "wb") as f:
            f.write(data)
        print(f"EXTRACTED {t} <- {os.path.basename(dat)} ({size} bytes) -> {outp}")


if __name__ == "__main__":
    main()
