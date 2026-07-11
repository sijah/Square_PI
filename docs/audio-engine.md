# SquarePi Audio Engine™ — Technical Deep Dive

Every audio source — regardless of protocol, sample rate, or bit depth — passes through four processing stages before reaching the speakers. All four run automatically with no configuration.

The stages in order:

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

The Pi clock is approximately **10× more accurate** at 48kHz than at 44.1kHz — the 44.1kHz clock has a constant ~1.8 ppm offset baked into the fractional divider. 48kHz is the Pi's native audio operating point, so that's what the whole pipeline runs at.

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

The filter runs in a single pass. The "very high" quality setting uses a longer filter kernel with tighter stopband attenuation.

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
| `very high` | SquarePi default |
| `ultra high` | Mastering (high CPU, not practical on Zero 2W) |

`very high` is the practical maximum for the Pi Zero 2W — it runs without audible dropouts at 44100→48000 on the Zero 2W's quad-core Cortex-A53.

---

## Stage 3 — SquarePi Mixer™

### What it does

Shares a single audio output device among multiple simultaneous sources using ALSA's software mixing (dmix) facility.

### Why it's needed

Hardware audio devices are exclusive-access by default — only one application can use the output at a time. ALSA dmix creates a virtual shared PCM device that multiple applications write to simultaneously.

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

- **rate / format**: All sources are mixed at 48kHz S32_LE — this is why upscaling and resampling must run first
- **period_size / buffer_size**: Sized large (65536 frames) to prevent underruns when multiple heavy sources (MPD + Bluetooth) play simultaneously
- **ipc_key**: Shared memory key used by ALSA for inter-process coordination

All audio applications — MPD, BlueALSA (Bluetooth), upmpdcli (DLNA), shairport-sync (AirPlay) — write to `squarepi_mix`. The dmix layer sums all streams in real time and feeds a single stream to the hardware.

### Bluetooth audio path

Bluetooth has an extra stage before the mixer — a softvol PCM that provides independent volume control for the BT path:

```
Phone (A2DP)
    │
    ▼
bluealsa daemon ── AVRCP volume applied to PCM samples (--a2dp-volume)
    │
    ▼
squarepi_bt_vol ── ALSA softvol (BT Volume control, −40 dB to 0 dB)
    │
    ▼
squarepi_mix ───── shared dmix (same as all other sources)
```

**AVRCP volume** — when a phone supports AVRCP absolute volume, the bluealsa daemon intercepts the volume command and applies a gain directly to the decoded PCM samples before they reach squarepi_bt_vol. The Pi receives quieter or louder samples; no ALSA control changes.

**BT Volume softvol** — the `squarepi_bt_vol` PCM is an ALSA softvol device sitting between bluealsa-aplay and dmix. It exposes a `BT Volume` mixer control (numid=40 on LouderRaspberry, range 0–99, −40 dB to 0 dB). The EQ UI slider maps 0–100% to this range.

| EQ UI % | ALSA val | dB |
|---|---|---|
| 0% | 0 | −40.0 dB |
| 25% | 25 | −29.9 dB |
| 50% | 50 | −19.8 dB |
| 75% | 74 | −10.1 dB |
| 100% | 99 | 0.0 dB |

Default is **50%** (−20 dB). The value is persisted to `/var/lib/squarepi/bt_volume` and restored within 1 second of each BT audio start — including after reboots and mid-session reconnects.

**`BT Volume` control lifetime** — the softvol control only exists while `squarepi_bt_vol` PCM is open (i.e. while BT audio is actively playing). It is not present in `amixer` output when no BT device is streaming. Use `cget`/`cset`, not `sget`/`sset`:

```bash
amixer -c LouderRaspberry cget "name=BT Volume"
amixer -c LouderRaspberry cset "name=BT Volume" 50
```

### Multiple simultaneous sources

The dmix layer supports many simultaneous writers. Multiple Bluetooth devices, MPD clients, DLNA, and AirPlay can all produce audio at the same time without interrupting each other.

---

## Stage 4 — SquarePi EQ™

### What it does

15-band parametric equalizer running inside the TAS5805M chip. The Pi CPU handles no audio processing for equalization — it just sends I²C commands and the chip does the rest.

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
- Range: 0–110 (110 = 0 dB) — inferred from driver, not Pi-verified
- Formula: `L_raw = 110 - max(0, balance)` / `R_raw = 110 - max(0, -balance)`

### Persisting EQ state

Settings are saved via ALSA state file:

```bash
sudo alsactl store
```

Restored at every boot by `squarepi-alsa-restore.service` (runs before MPD starts). The EQ UI **Save to chip** button calls this automatically.

---

## Gain staging & headroom

Understanding where level is added and removed matters, because **boost stages sit after the volume control** — so it's possible to clip in ways the volume knob can't undo.

The full chain, in order:

```
ReplayGain → MPD software volume → soxr → dmix (sums sources)
   → [ TAS5805M:  Digital Volume → 15-band EQ → Analog Gain ] → speakers
```

Key facts:

- **`Digital Volume` (ALSA `numid=1`, 0–127).** Value **103 = 0 dB (unity)** — this is the chip default and the safe ceiling. Each step is 0.5 dB; **127 = +24 dB**. SquarePi pins it to 103 on first boot and persists it. **Do not raise it past 103** — in `alsamixer` it shows as "81%", which tempts a push to 100% = +24 dB of digital gain = guaranteed clipping and possible speaker damage.
- **EQ boost is applied *after* the volume control**, inside the chip. A large positive band (up to +15 dB) on hot content can overflow the biquad regardless of how low MPD's volume is set. Keep big boosts moderate, or trim **Analog Gain** down to reserve headroom.
- **dmix sums simultaneous sources.** Two sources near full scale can sum past 0 dBFS. There is no hardware limiter — the TAS5805M's DRC is not exposed by the driver — so headroom is managed by keeping levels sensible, not by a brickwall.
- **`Analog Gain`** (0 to −15.5 dB, default 0 dB) is the right place to set a **system ceiling**: pull it down a few dB to match the amp to your speakers so the useful volume range spreads across the whole knob instead of bunching at the bottom.

### Loudness consistency across a mixed library

SquarePi ships with `replaygain "off"` for predictable behaviour. If a music collection sounds inconsistent track-to-track (common with mixed-source MP3s that carry no gain tags), tag it once with **loudgain** — real EBU R128 normalisation:

```bash
sudo apt install loudgain
loudgain -a -k -s e /var/lib/mpd/music/usb/*/**/*.mp3   # album mode, clip-safe
mpc update
```

Then set `replaygain "album"` (or `"track"`) in `/etc/mpd.conf` and restart MPD to use the tags.

---

## Hardware DSP specifications

| Parameter | Value |
|---|---|
| THD+N | ≤ 0.03% at 1W, 1kHz |
| SNR | up to 107 dB (A-weighted, 24V / 8Ω) |
| Dynamic range | up to 106 dB (A-weighted, 24V / 8Ω) |
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

The DSP UI polls these registers and displays live status. All faults self-clear when the condition resolves (e.g. speaker short removed, supply voltage normalised).

---

## Driver

The audio driver is the `tas58xx` kernel module from [sonocotta/tas5805m-driver-for-raspbian](https://github.com/sonocotta/tas5805m-driver-for-raspbian).

The installer auto-detects the TAS5805M I²C address (scans 0x2c–0x2f on buses 1 and 2) and writes the correct `dtoverlay=tas58xx,i2creg=<address>` to the boot config.
