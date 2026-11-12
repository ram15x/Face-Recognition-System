function describe(error) {
  switch (error.name) {
    case 'NotAllowedError': return 'Camera permission was denied. Allow it in the address bar, then try again.';
    case 'NotFoundError': return 'No camera was found.';
    case 'NotReadableError': return 'The camera is being used by another app.';
    default: return `Could not start the camera (${error.name}).`;
  }
}

export class Camera {
  constructor(video, stage) {
    this.video = video;
    this.stage = stage;
    this.stream = null;
    this.canvas = document.createElement('canvas');
  }

  get active() { return this.stream !== null; }
  get ready() { return this.active && this.video.videoWidth > 0 && this.video.readyState >= 2; }

  async start() {
    if (this.stream) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Camera access needs HTTPS or localhost.');
    }
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
        audio: false,
      });
    } catch (error) {
      throw new Error(describe(error));
    }
    this.video.srcObject = this.stream;
    await this.video.play();
    if (this.video.videoWidth) {
      this.stage.style.aspectRatio = `${this.video.videoWidth} / ${this.video.videoHeight}`;
    }
  }

  stop() {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.video.srcObject = null;
  }

  /** Grab the current frame as a JPEG, downscaled so uploads stay small. */
  capture(maxSide = 640, quality = 0.85) {
    const { videoWidth: width, videoHeight: height } = this.video;
    const scale = Math.min(1, maxSide / Math.max(width, height));
    this.canvas.width = Math.round(width * scale);
    this.canvas.height = Math.round(height * scale);
    this.canvas.getContext('2d').drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
    return new Promise((resolve, reject) => {
      this.canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error('Could not capture a frame.'))),
        'image/jpeg',
        quality,
      );
    });
  }
}
