# FaceAttend

[![CI](https://github.com/ram15x/Face-Recognition-System/actions/workflows/ci.yml/badge.svg)](https://github.com/ram15x/Face-Recognition-System/actions/workflows/ci.yml)

Face recognition attendance that runs in the browser. People register once in front of the webcam, then are marked present automatically when they walk up to the camera. A dashboard shows who is in, who is missing, and exports CSV.

![Attendance dashboard](docs/dashboard.png)

*Screenshots use made-up demo data (`python -m faceattend.demo`).*

## What it does

- **Scan**: live camera view with a box and name over every recognised face. Several people in one frame work.
- **Register**: a guided capture (five shots, with prompts to turn your head slightly). The server checks each shot has exactly one clear, large-enough face.
- **Dashboard**: present and absent lists for any day, a 14-day trend, CSV export, and deleting a person.
- **Unknown faces stay unknown.** A stranger is never forced onto the nearest registered name.
- **No double entries.** Attendance is recorded once per person per day.
- **Confirm before marking.** A person must be recognised twice within a few seconds, so a single bad frame cannot mark the wrong person.
- **Duplicate-face check** at registration, so the same person cannot be enrolled twice under different names.

![Register screen](docs/register.png)

## Quick start

You need [Python](https://www.python.org/downloads/) 3.11 or newer.

```bash
git clone https://github.com/ram15x/Face-Recognition-System.git
cd Face-Recognition-System

python -m venv .venv
# Windows:   .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
python -m faceattend.models      # downloads the two model files (about 38 MB), once
python -m faceattend             # starts the server
```

Open <http://127.0.0.1:8000>. Browsers only allow camera access on `localhost` or over HTTPS, so use that address rather than your computer's network address.

### With Docker

```bash
docker compose up --build
```

The models are downloaded while the image builds, and the data lives in a Docker volume.

## Configuration

Everything is an environment variable, so there is nothing to edit.

| Variable | Default | What it does |
| --- | --- | --- |
| `ATTENDANCE_ADMIN_TOKEN` | *(unset)* | If set, registering, listing, deleting and exporting need this token. Scanning stays open so a kiosk works without logging in. **Set this if the server is reachable by anyone else.** |
| `ATTENDANCE_MATCH_THRESHOLD` | `0.40` | Minimum cosine similarity to accept a match. Raise it for fewer wrong matches, lower it if people are often not recognised. |
| `ATTENDANCE_CONFIRM_HITS` | `2` | Sightings needed before attendance is recorded. |
| `ATTENDANCE_CONFIRM_WINDOW_S` | `6` | The time window for those sightings, in seconds. |
| `ATTENDANCE_DETECT_THRESHOLD` | `0.85` | Minimum detector confidence for a face to count. |
| `ATTENDANCE_MIN_FACE_PX` | `80` | Smallest face accepted at registration. |
| `ATTENDANCE_DATA_DIR` | `./data` | Where the database is kept. |
| `ATTENDANCE_MODELS_DIR` | `./models` | Where the model files are kept. |

For example, on Windows PowerShell: `$env:ATTENDANCE_ADMIN_TOKEN = "choose-something-long"` before `python -m faceattend`.

## How it works

```
browser camera ──JPEG frame──▶ POST /api/recognize
                                   │
                  YuNet finds faces │  (OpenCV, ONNX)
                                   ▼
                  SFace turns each face into 128 numbers
                                   │
              compare with every stored embedding (cosine similarity)
                                   │
        ┌──────────────────────────┴──────────────────────────┐
   below threshold                                     above threshold
   "Unknown"                              seen twice in a few seconds?  ──▶ record attendance
```

- **YuNet** (face detection) and **SFace** (face embedding) come from the [OpenCV Zoo](https://github.com/opencv/opencv_zoo) and run through OpenCV's own DNN module, so there is no PyTorch, TensorFlow or dlib to install.
- The server is **FastAPI**, storage is **SQLite**, and the front end is plain JavaScript with no build step.
- The camera is read **in the browser** and frames are uploaded, so the same code works on a laptop, a kiosk or a server.

## Privacy and limits

- Only **embeddings** (128 numbers per sample) are stored. **No photos are saved.** An embedding is still biometric data, so treat it with the same care as a photo.
- Registration requires an explicit consent tick, and **deleting a person removes their embeddings and attendance history**.
- The `data/` folder holds biometric data. It is git-ignored; keep it that way and back it up carefully.
- **There is no liveness check.** A printed photo or a phone screen held to the camera can fool it. Do not use this for anything security-critical.
- Face recognition is less reliable in poor light, at steep angles and for some groups of people more than others. Tune the threshold on your own users, and keep a manual fallback.

## Development

```bash
pip install -r requirements-dev.txt
python -m faceattend.models
python -m pytest        # unit, API and real-model tests
ruff check . && ruff format --check .
```

The app logic (matching, rules, API) is tested with a stand-in face engine, so those tests run without the models. `tests/test_real_models.py` runs the real YuNet and SFace models and is skipped until they are downloaded. CI downloads them and runs everything on Python 3.11 and 3.13, then builds the Docker image and checks it starts.

```
faceattend/
  app.py        HTTP API, admin token, security headers
  service.py    registration and attendance rules
  faces.py      YuNet + SFace wrapper
  matching.py   similarity search with unknown rejection
  db.py         SQLite storage
  models.py     model downloader
  static/       the web UI (HTML, CSS, JavaScript)
tests/
```


## Credits

- Face detection: **YuNet**, face recognition: **SFace**, both from the OpenCV Zoo (MIT and Apache-2.0 licensed).
- [OpenCV](https://opencv.org/), [FastAPI](https://fastapi.tiangolo.com/).

Released under the [MIT License](LICENSE).
