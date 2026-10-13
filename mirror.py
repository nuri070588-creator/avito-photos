"""Зеркало фото объектов с публичной папки Яндекс Диска для объявлений Авито.

Берёт только фото, которые бот ставит в объявления: подпапка «авито» в папке
объекта (если её нет — картинки в самой папке объекта). Папку «документы» не трогает.
Файлы называются по md5 оригинала (без адресов и названий), сжимаются до 2000 px.
Ссылка на фото: https://raw.githubusercontent.com/nuri070588-creator/avito-photos/main/p/<md5>.jpg
"""
import io
import json
import os
import sys

import requests
from PIL import Image, ImageOps

PUBLIC_URL = os.environ.get("YADISK_PUBLIC_URL") or "https://disk.yandex.ru/d/RjKdL7CJbBlZ1Q"
API = "https://cloud-api.yandex.net/v1/disk/public/resources"
FIELDS = ("_embedded.items.name,_embedded.items.type,_embedded.items.mime_type,"
          "_embedded.items.file,_embedded.items.path,_embedded.items.md5,_embedded.total")
SKIP_TOP = ("продал", "сдали", "продан")
MAX_PHOTOS = 40          # как в боте: больше Авито не принимает
MAX_NEW_PER_RUN = 600   # остальное догрузится в следующий запуск
MAX_SIDE = 2000
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "p")


def ls(path):
    items, offset = [], 0
    while True:
        r = requests.get(API, params={"public_key": PUBLIC_URL, "path": path, "limit": 200,
                                      "offset": offset, "fields": FIELDS}, timeout=60)
        r.raise_for_status()
        emb = r.json().get("_embedded") or {}
        chunk = emb.get("items") or []
        items += chunk
        offset += len(chunk)
        if not chunk or offset >= (emb.get("total") or 0):
            return items


def is_img(i):
    return i.get("type") == "file" and (i.get("mime_type") or "").startswith("image/") and i.get("md5")


def wanted():
    """Все фото, которые бот может поставить в объявление."""
    out = []
    for top in ls("/"):
        if top.get("type") != "dir":
            continue
        for sub in ls(top["path"]):
            name = (sub.get("name") or "").lower()
            if sub.get("type") != "dir" or any(s in name for s in SKIP_TOP):
                continue
            items = ls(sub["path"])
            pick = [i for i in items if i.get("type") == "dir" and (i.get("name") or "").strip().lower() == "авито"]
            src = ls(pick[0]["path"]) if pick else items
            imgs = sorted((i for i in src if is_img(i)), key=lambda i: i.get("name") or "")
            out += imgs[:MAX_PHOTOS]
    return out


def save(item, dst):
    r = requests.get(item["file"], timeout=120)
    r.raise_for_status()
    im = Image.open(io.BytesIO(r.content))
    im = ImageOps.exif_transpose(im).convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    im.save(dst, "JPEG", quality=85, optimize=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    have = {f[:-4] for f in os.listdir(OUT) if f.endswith(".jpg")}
    new = errors = 0
    for item in wanted():
        m = item["md5"]
        if m in have:
            continue
        if new >= MAX_NEW_PER_RUN:
            break
        try:
            save(item, os.path.join(OUT, m + ".jpg"))
            have.add(m)
            new += 1
        except Exception as e:  # битый файл не должен останавливать всё
            errors += 1
            print("skip", m, e, file=sys.stderr)
    with open(os.path.join(ROOT, "index.json"), "w", encoding="utf-8") as f:
        json.dump(sorted(have), f)
    print(f"новых фото: {new}, всего: {len(have)}, ошибок: {errors}")


if __name__ == "__main__":
    main()
