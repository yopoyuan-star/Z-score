# 台股 480天 Z-SCORE + 日週月動態 KD(每日自動更新)

每個平日台北 14:00(UTC 06:00),GitHub Actions 會:
1. 從證交所抓加權指數每日開高低收,補進 `data/taiex.csv`(2003-12-19 起,種子資料取自你的「輸入」工作表)
2. 計算「480天Z-SCORE -2.0」工作表的全部欄位,以及日/週/月動態 KD
3. 產生 `docs/zscore.html`(網頁)與 `docs/zscore_output.csv`(最近 300 天完整欄位)

## 部署
1. 全部檔案(含隱藏資料夾 `.github`)推上 GitHub。
2. Settings → Pages → Deploy from a branch → `main` / `/docs`。
3. Actions → `Daily Z-SCORE update` → Run workflow(手動執行會強制重建頁面)。
4. 網址:`https://<帳號>.github.io/<repo>/zscore.html`

## 放進既有 repo(例如 MA200-240)
複製 `model.py`、`fetch_twse.py`、`build.py`、`data/taiex.csv`、`.github/workflows/daily-zscore.yml`,
`requirements.txt` 補上 `numpy`。輸出檔名是 `zscore.html`,不會蓋掉原本的 `index.html`。

## 本機測試
`pip install -r requirements.txt && python build.py`(會真的連證交所;`FORCE=1` 可強制重建)
