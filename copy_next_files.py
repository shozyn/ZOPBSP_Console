from pathlib import Path
import shutil, msvcrt

pairs = [
    (r"C:\Pi_loc\LA\RPI1\GPS",       r"C:\Pi\RPI1\bsp\GPS"),
    (r"C:\Pi_loc\LA\RPI2\GPS",       r"C:\Pi\RPI2\bsp\GPS"),
    (r"C:\Pi_loc\LA\RPI3\GPS",       r"C:\Pi\RPI3\bsp\GPS"),
    (r"C:\Pi_loc\LA\RPI1\streaming", r"C:\Pi\RPI1\bsp\streaming"),
    (r"C:\Pi_loc\LA\RPI2\streaming", r"C:\Pi\RPI2\bsp\streaming"),
    (r"C:\Pi_loc\LA\RPI3\streaming", r"C:\Pi\RPI3\bsp\streaming"),
]

files = [[p for p in Path(src).iterdir() if p.is_file()] for src, _ in pairs]
for group in files:
    group.sort(key=lambda p: p.name.lower())

i = 0
print("Press 'n' to copy the next file from each folder. Press 'q' to quit.")

while True:
    key = msvcrt.getwch().lower()
    if key == "q":
        break
    if key != "n":
        continue

    copied = 0
    for group, (_, dst) in zip(files, pairs):
        if i < len(group):
            Path(dst).mkdir(parents=True, exist_ok=True)
            shutil.copy2(group[i], Path(dst) / group[i].name)
            print(f"Copied: {group[i]} -> {dst}")
            copied += 1

    if copied == 0:
        print("No more files to copy.")
        break

    i += 1
