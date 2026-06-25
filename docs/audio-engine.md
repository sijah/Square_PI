# SquarePi Audio Engine™ — Technical Deep Dive

The SquarePi Audio Engine™ is a four-stage automatic audio processing pipeline that runs on every SquarePi system. Every audio source — regardless of protocol, sample rate, or bit depth — passes through all four stages before reaching the speakers.

The stages run in this order:

```
Source audio
    │
    ▼
SquarePi Upscaler™  ─── 48kHz / 24-bit target
    │
    ▼
SquarePi Resampler™ ─── SoXR polyphase (if rate conversion needed)
    │
    ▼
SquarePi Mixer™     ─── ALSA dmix 48kHz / S32_LE
    │
    ▼
SquarePi EQ™        ─── TAS5805M hardware DSP over I²C
    │
    ▼
Speakers
```

No configuration required. All four stages are active automatically from first boot.

---

## Stage 1 — SquarePi Upscaler™

### What it does

All audio is converted to **48kHz / 24-bit** before any other processing. Sources that are already at 48kHz pass through unchanged. Sources at 44.1kHz, 32kHz, or other rates are upsampled by the SquarePi Resampler™ (Stage 2).

### Why 48kHz?

The Raspberry Pi generates its audio master clock from the on-chip PLL (PLLD, 500MHz) using a fractional divider.

| Target rate | Clock error |
|---|---|
| 44.1 kHz | ~1.8 ppm |
| 48 kHz | ~0.16 ppm |

The Pi clock is approximately **10× more accurate** at 48kHz than at 44.1kHz. Operating at 44.1kHz introduces a small but measurable frequency error that accumulates over time. 48kHz is the Pi's native audio operating point.

This is why SquarePi runs its entire pipeline at 48kHz regardless of source material.

### Why 24-bit?

The MPD audio format is configured as `48000:24:2`. MPD outputs 24-bit samples even when the source is 16-bit (standard CD quality). The ALSA dmix layer runs at S32_LE (32-bit) to preserve 24-bit content without truncation — 24-bit values fit cleanly into 32-bit signed integers with no loss.

### MPD configuration

```conf
audio_format    "48000:24:2"
format          "48000:24:2"
```

ALSA dmix (`/etc/asound.conf`):
```conf
rate        48000
format      S32_LE
```

---

## Stage 2 — SquarePi Resampler™

### What it does

Converts any source sample rate to 48kHz using SoXR — the Secret Rabbit Code Resampler, a polyphase resampling library used in professional mastering and broadcast tools.

### When it runs

| Source | Action |
|---|---|
| 48kHz | Pass-through — no conversion |
| 44.1kHz (CD, MP3, most streaming) | 44100 → 48000 Hz resampling |
| 32kHz (some radio streams) | 32000 → 48000 Hz resampling |
| 96kHz (hi-res) | 96000 → 48000 Hz downsampling |

### The 44100 → 48000 conversion

The ratio 44100:48000 simplifies to **147:160**. SoXR implements this as a polyphase filter bank with an integer upsampling/downsampling approach:

1. Upsample by 160 (insert 159 zeros between each sample)
2. Apply anti-aliasing low-pass filter
3. Downsample by 147 (keep every 147th sample)

The filter is applied once, not in two separate passes. The "very high" quality setting uses a longer filter kernel with tighter stopband attenuation, producing a conversion that is audibly transparent.

### MPD configuration

```conf
resampler {
    plugin    "soxr"
    quality   "very high"
}
```

### SoXR quality levels

| Setting | Use case |
|---|---|
| `quick` | Real-time with minimal CPU |
| `medium` | General purpose |
| `high` | High quality |
| `very high` | SquarePi default — studio-grade |
| `ultra high` | Mastering (high CPU, not practical on Zero 2W) |

`very high` is the practical maximum for the Pi Zero 2W — it runs without audible dropouts at 44100→48000 on a single-core Arm Cortex-A53.

---

## Stage 3 — SquarePi Mixer™

### What it does

Shares a single audio output device among multiple simultaneous sources using ALSA's software mixing (dmix) facility.

### Why it's needed

Hardware audio devices are exclusive-access by default. Without a mixer, only one application can use the audio output at a time. The SquarePi Mixer™ solves this by creating a virtual shared device that multiple applications write to simultaneously.

### How it works

ALSA dmix is configured as a virtual PCM device in `/etc/asound.conf`:

```conf
pcm.squarepi_mix {
    type dmix
    ipc_key 1024
    slave {
        pcm         "hw:LouderRaspberry,0"
        rate        48000
        format      S32_LE
        period_size 4096
        buffer_size 65536
    }
}
pcm.!default squarepi_mix
```

- **rate / format**: All sources are mixed at 48kHz S32_LE — this is why the SquarePi Upscaler™ and Resampler™ must run first
- **period_size / buffer_size**: Sized large (65536 frames) to prevent underruns when multiple heavy sources (MPD + Bluetooth) play simultaneously
- **ipc_key**: Shared memory key used by ALSA for inter-process coordination

All audio applications — MPD, BlueALSA (Bluetooth), upmpdcli (DLNA), shairport-sync (AirPlay) — write to `squarepi_mix`. The dmix layer sums all streams in real time and feeds a single stream to the hardware.

### Up to 10 simultaneous sources

The dmix layer supports many simultaneous writers. In practice, 10 devices can connect via different protocols (multiple Bluetooth devices, multiple MPD clients, DLNA) and all produce audio at the same time without interrupting each other.

---

## Stage 4 — SquarePi EQ™

### What it does

15-band parametric equalizer running inside the TAS5805M amplifier chip. The equalization happens entirely in hardware — the Pi CPU does zero audio processing for EQ.

### How it works — hardware path

The TAS5805M chip contains a programmable biquad filter bank. Each of the 15 EQ bands is implemented as a second-order IIR (biquad) filter with five coefficients. The ALSA driver (tas58xx) translates amixer control changes into I²C writes that update the filter coefficients inside the chip.

```
amixer sset "00200 Hz" -- -3
  │
  ▼
tas58xx_eq_put() in the kernel driver
  │
  ▼
Coefficient lookup in tas5805m_eq.h (302KB pre-computed table)
  │
  ▼
I²C write sequence to TAS5805M registers (book/page switching)
  │
  ▼
Hardware filter active immediately
```

Changes take effect within one I²C transaction cycle — effectively instant. The driver defers writes if audio is not currently playing and flushes them on `TRIGGER_START`.

### ALSA control names (exact strings)

```
"00020 Hz"   "00032 Hz"   "00050 Hz"   "00080 Hz"   "00125 Hz"
"00200 Hz"   "00315 Hz"   "00500 Hz"   "00800 Hz"   "01250 Hz"
"02000 Hz"   "03150 Hz"   "05000 Hz"   "08000 Hz"   "16000 Hz"
```

Value range: **−15 to +15** (integer, 1 unit = 1 dB). Center 0 = flat.

Note: `alsamixer` displays percentages (0–100%), not dB values. 50% = flat (0 dB), 100% = +15 dB, 0% = −15 dB.

### Why the `--` separator matters

`amixer` passes arguments to getopt. Negative values like `-3` are parsed as unknown flags and silently discarded — only positive EQ adjustments would be applied. All SquarePi scripts and the eq-server use `--` to terminate option parsing:

```bash
amixer -c LouderRaspberry sset "00200 Hz" -- -3
```

```python
subprocess.run(["amixer", "-c", CARD, "sset", control, "--", str(value)])
```

### EQ bypass

```bash
amixer -c LouderRaspberry sset "Equalizer" Off   # bypass — flat passthrough
amixer -c LouderRaspberry sset "Equalizer" On    # EQ active
```

### Additional DSP controls

**Analog Gain** — hardware output level trim:
- ALSA control: `"Analog Gain"`
- Range: 0–31 (31 = 0 dB, each step = 0.5 dB)
- Full range: 0 dB to −15.5 dB

**Mixer Mode** — signal routing:
- Control: `"Mixer Mode"`
- Values: `Stereo` / `Mono` / `Left` / `Right`
- Custom crossfeed: `"Mixer L2L Gain"`, `"Mixer R2L Gain"`, `"Mixer L2R Gain"`, `"Mixer R2R Gain"` (−110 to 0 dB)

**Balance** — per-channel gain:
- Controls: `"Channel Left Gain"`, `"Channel Right Gain"`
- Range: 0–110 (110 = 0 dB)
- Formula: `L_raw = 110 - max(0, balance)` / `R_raw = 110 - max(0, -balance)`

### Persisting EQ state

Settings are saved via ALSA state file:

```bash
sudo alsactl store
```

Restored at every boot by `squarepi-alsa-restore.service` (runs before MPD starts). The EQ UI **Save to chip** button calls this automatically.

---

## Hardware DSP specifications

| Parameter | Value |
|---|---|
| THD+N | ≤ 0.03% at 1W, 1kHz |
| SNR | ≥ 107 dB (A-weighted) |
| Dynamic range | 106 dB (A-weighted) |
| Crosstalk | −100 dB at 1kHz |
| Idle noise | < 40 µVRMS |
| Parametric EQ | 15 bands per channel, full biquad |
| DRC | 3-band, 4th-order dynamic range compression |
| Volume range | +24 dB to −103 dB, 0.5 dB steps |
| Sample rates | 32 / 44.1 / 48 / 88.2 / 96 kHz |
| Switching frequency | 384 / 480 / 576 / 768 kHz |

---

## Fault monitoring

The TAS5805M exposes hardware fault flags as read-only ALSA controls:

| Control | Meaning |
|---|---|
| `Fault Left Channel OC` | Left output overcurrent |
| `Fault Right Channel OC` | Right output overcurrent |
| `Fault Left Channel DC` | Left DC fault |
| `Fault Right Channel DC` | Right DC fault |
| `Fault PVDD Undervoltage` | Supply too low |
| `Fault PVDD Overvoltage` | Supply too high |
| `Fault Clock` | I2S clock fault |
| `Fault OTP CRC Error` | Internal config error |
| `Fault Over Temperature Shutdown` | Chip too hot |
| `Warning Over Temperature 112C` | Thermal warning |
| `Warning Over Temperature 122C` | Thermal warning |
| `Warning Over Temperature 134C` | Thermal warning |
| `Warning Over Temperature 146C` | Thermal warning |

The SquarePi EQ™ DSP UI polls these registers and displays live status. All faults self-clear when the condition resolves (e.g. speaker short removed, supply voltage normalised).

---

## Driver

The audio driver is the `tas58xx` kernel module from [sonocotta/tas5805m-driver-for-raspbian](https://github.com/sonocotta/tas5805m-driver-for-raspbian).

The installer auto-detects the TAS5805M I²C address (scans 0x2c–0x2f on buses 1 and 2) and writes the correct `dtoverlay=tas58xx,i2creg=<address>` to the boot config.
