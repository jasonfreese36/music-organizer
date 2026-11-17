# Audio tuning in v1.5

[简体中文](AUDIO_TUNING.zh-CN.md) · [Project home](../README.md)

Open **Advanced → Audio tuning**. First launch retains the existing processing defaults: SWR, original PCM sample rates, ordinary DSD conversion, no gain change and no custom cutoff. Settings are saved locally and included in exported processing profiles.

## Resampling choices

| Engine / filter | Controls |
|---|---|
| **SoXR** | HQ 20-bit, VHQ 28-bit or custom 15–33-bit calculation precision; optional Chebyshev mode |
| **SWR · Kaiser** | Windowed sinc; filter length 4–256, phase-table precision 0–16, Kaiser beta 2–16, exact rational ratios |
| **SWR · Blackman–Nuttall** | Windowed sinc with a different window; SWR length and phase-table controls |
| **SWR · Cubic** | Cubic interpolation for a speed-focused alternative |

Calculation precision is separate from output bit depth. Phase-table precision does not select minimum or linear phase. Controls belonging to the inactive engine are disabled.

Enable **Custom cutoff ratio** to start at **98%**, adjustable from 80 to 99.7%. The percentage is relative to the applicable Nyquist frequency: SWR defines its −6 dB cutoff, while SoXR defines its 0 dB passband point. Equal percentages do not describe identical filter responses. With custom cutoff disabled, the engine default is used. See the [FFmpeg resampler options](https://ffmpeg.org/ffmpeg-resampler.html).

Choose an output rate policy under **Audio conversion**. Filter settings alone do not force an existing same-rate FLAC to be re-encoded. **Downsample within the 44.1 / 48 kHz family** keeps related rates where possible: at a 96 kHz ceiling, 176.4 kHz becomes 88.2 kHz, while 192 kHz becomes 96 kHz. Format and Apple device limits take priority.

## Dither and level

Dither acts at final integer output when quantization is needed. Options include rectangular, triangular, high-pass triangular and the bundled engine's noise-shaping filters. Unsupported noise-shaping/rate combinations produce an error instead of FFmpeg's silent fallback. Triangular dither supports every offered rate. The amplitude defaults to 1; 0 disables added noise.

**Output gain / headroom** is a fixed −24 to +6 dB adjustment, with 0 as default. Negative gain leaves headroom; positive gain can clip. No automatic loudness normalization or limiter is applied. Optional downmix-matrix normalization reduces matrix overload during multichannel downmixing; it is not a true-peak limiter. Existing MP3/AAC payloads retain their level until re-encoding is enabled.

## DSD to PCM

Enable **Advanced DSD processing** to apply the same path to DSF, DFF and SACD ISO. ISO is first extracted to DSD, including DST decoding where needed. FFmpeg's DSD decoder has a fixed FIR; this version exposes subsequent PCM processing, rather than claiming interchangeable DSD decimation algorithms.

| Control | Behavior |
|---|---|
| **PCM rate** | 44.1, 48, 88.2, 96, 176.4, 192, 352.8 or 384 kHz, selected under Audio conversion |
| **DSD PCM bit depth** | 16 / 24 / 32 bit for FLAC; compatible ALAC is bounded by Apple limits |
| **DSD gain** | −24 to +12 dB; added to output gain; default 0, with no automatic +6 dB |
| **Ultrasonic low-pass** | 0 disables it; otherwise 20–100 kHz, default 30 kHz; bounded below the decoded PCM Nyquist frequency |
| **Low-pass order** | 2 / 4 / 6 / 8-order double-precision Butterworth IIR; affects phase response |
| **DC removal** | Optional 5 Hz second-order high-pass |

The order is **decode → DC removal / low-pass → gain → final rate conversion and channel mapping → integer quantization / dither → encoding**. The low-pass runs before final downsampling. The preview displays the applied filter cutoff, gain, resampler and output format.

Advanced DSD processing is off initially. Ordinary SACD extraction retains the existing native FLAC path at its supported rates; other requested rates use DSD extraction followed by FFmpeg conversion. Source files remain in place, and the selected original-archive policy is retained.

## Repeat runs and verification

Active DSP settings are recorded in the library index. Repeating the same settings reuses completed outputs; changing them rebuilds the relevant output from the original source. Restoring unprocessed PCM also reads the original source. Processed audio is checked for format, duration and complete decoding; sample-identical verification applies only when PCM is expected to remain unchanged.

Generated-audio tests measure cutoff response, DSD gain, ultrasonic attenuation and DC removal, and check rates, Apple limits and resume behavior. The ISO extraction boundary is checked with generated DSD/XML fixtures; a real-disc listening comparison is not claimed.
