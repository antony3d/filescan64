🇬🇧 English | [🇷🇺 Русский](README_ru.md)

# FileScan64 v0.9.2

Modern Python/Tkinter reimplementation of the classic disk read-speed tester. Sequentially reads every file in a folder tree and reports per-file and global throughput.

### Screenshots

![FileScan64](img/filescan64.png)



### Features

- Scan tree startup directory selection
- Run statistics: volume — files, folders, MB read; speed — avg / min / max (per-file and global)
- Optional global progress with tree size pre-scan + ETA
- Per-file progress bar only for files > 100 MB
- Error & event log

### Requirements & Run

Python 3 + `tkinter`, no dependencies. Linux / Windows.

```bash
python3 filescan64.py
```

### Constants

| Constant | Value | Meaning |
|---|---|---|
| `BUFFER_SIZE` | 256 KB | read chunk |
| `LARGE_FILE_THRESHOLD` | 50 MB | volume threshold for UI updates |
| `PROGRESS_FILE_MIN` | 100 MB | show per-file progress |
| `UI_UPDATE_INTERVAL` | 0.25 s | minimum UI update interval |

## Based on

```
FileScan32 Version 1.06
Built date: Wed Oct 4 17:13:46 1995

Copyright 1995 Jack Naoumov, Jack_N@MSN.com.
All rights reserved. This product is freeware.
```

![FileScan32 1.06](img/filescan32.png)

## License

MIT — see [LICENSE](LICENSE).
