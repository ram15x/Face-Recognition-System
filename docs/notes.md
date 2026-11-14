# Notes for running it

Things worth knowing before you rely on FaceAttend.

- There is no liveness check. A printed photo or a phone screen held up to the camera can be accepted as a face. Don't use it for anything security-critical.
- Face recognition is less reliable in poor light, at steep angles, and for some groups of people more than others. Tune `ATTENDANCE_MATCH_THRESHOLD` on your own users and keep a manual fallback.
- An embedding is biometric data even though it isn't a photo. Treat the `data/` folder with the same care, and back it up carefully.
- Set `ATTENDANCE_ADMIN_TOKEN` whenever the server can be reached by anyone else.
