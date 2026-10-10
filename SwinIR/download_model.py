"""Download only the requested official Classical SR x2 checkpoint."""
from pathlib import Path
import hashlib
import urllib.request

NAME = '001_classicalSR_DF2K_s64w8_SwinIR-M_x2.pth'
MODEL = Path(__file__).resolve().parent / 'model_zoo' / 'swinir' / NAME
URL = 'https://github.com/JingyunLiang/SwinIR/releases/download/v0.0/' + NAME


def main():
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    if not MODEL.exists():
        partial = MODEL.with_suffix('.part')
        print(f'Downloading {NAME}', flush=True)
        with urllib.request.urlopen(URL, timeout=120) as response:
            expected = response.headers.get('Content-Length')
            with partial.open('wb') as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
        if expected and partial.stat().st_size != int(expected):
            raise RuntimeError('Incomplete checkpoint download; rerun download_model.py.')
        partial.replace(MODEL)
    with MODEL.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    print(f'{MODEL}\nBytes: {MODEL.stat().st_size}\nSHA256: {digest}')


if __name__ == '__main__':
    main()
