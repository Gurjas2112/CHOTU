# CHOTU app: flow-wise screenshots and full recording (demo data)

The Flutter app ran against its built-in **demo robot**. No hardware is connected; the demo world matches the Gazebo room. A scripted tour (`lib/tour.dart`) drives the app. `mobile_app/tools/record_app_demo.py` records it in headless Chromium at a phone viewport (430 × 932 CSS px).

**Full recording:** [`chotu_app_full_demo.mp4`](chotu_app_full_demo.mp4): 64 s, 860 × 1864, 30 fps, H.264. The amber strip at the top shows when the demo is fast-forwarding.

| # | Screen | t (s) |
|---|---|---|
| 01 | Connect: demo robot, or a rosbridge URL | 2.8 |
| 02 | Home: docked and ready, battery, bin, brush health | 7.3 |
| 03 | Cleaning started, undocking | 10.6 |
| 04 | Live map: 360° mapping scan | 14.5 |
| 05 | Live map: boustrophedon coverage | 20.7 |
| 06 | No-go zone edit mode | 23.9 |
| 07 | No-go zone drawn (sent through `/chotu/set_zones`) | 27.6 |
| 08 | Route re-planned around the zone | 31.3 |
| 09 | Home: brush-tangle alert | 34.6 |
| 10 | Alerts list | 38.1 |
| 11 | Schedules | 41.6 |
| 12 | Schedule added | 44.5 |
| 13 | Return to dock (`StartMission{abort: true}`) | 49.0 |
| 14 | Docked, mission complete | 53.2 |
| 15 | Cleaning history | 56.3 |
| 16 | Mission report with the AtomQuest rubric score | 59.6 |
| 17 | Settings / about | 63.7 |

`steps.json` holds the same timeline in machine-readable form.

## Re-record

```powershell
cd mobile_app\chotu_app
flutter build web --release --web-renderer html --dart-define=TOUR=true
cd ..\..
python mobile_app/tools/record_app_demo.py     # needs: pip install playwright && playwright install chromium; ffmpeg
```

Playwright records at CSS-pixel size. The script then upscales 2× with Lanczos and converts to a constant 30 fps, so the phone frame fills the video.
