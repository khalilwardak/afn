# AFN.af

A rates website that updates itself. Nothing here needs a server you manage.

- `site/` – the website (plain HTML). Deployed on Vercel.
- `collector/` – reads the Sarai Shahzada and Khorasan Market Telegram channels. Runs on GitHub Actions every 10 minutes.
- Da Afghanistan Bank rates are read from dab.gov.af/exchange-rates (at most once an hour, since the bank posts once a day). `config/dab.json` is only a backup used until the first successful read.
- The collector saves `rates.json` and a full price history (`events.jsonl`) on a branch called `data`.

How it flows: Telegram channel → collector (GitHub) → `data` branch → website reads `rates.json`.

## Set up (about 30 minutes)

1. **GitHub.** Create an account, then a new **public** repository (for example `afn`). Upload everything in this folder. If the hidden `.github` folder did not upload, click *Add file → Create new file*, type `.github/workflows/collect.yml` as the name and paste the contents of that file.
2. **Claude API key: optional, you can skip this.** The Sarai Shahzada boards are read with free OCR. A key only adds a backup for boards the OCR cannot read, and costs a cent or so each time it is used. To add one: create it at console.anthropic.com, then in your repo *Settings → Secrets and variables → Actions → New repository secret*, name `ANTHROPIC_API_KEY`.
3. **Test it.** *Actions → Collect rates → Run workflow → mode: probe*. It only looks at the two channels. Open the run log: you should see posts found, "with a photo" for Sarai Shahzada, and a line starting `dab:` with the bank's date and USD rate. Send me the log if anything looks wrong.
4. **Load history (once).** Run the workflow again with mode **backfill**, pages **10** (about 200 posts per channel). It also loads the bank's last 60 days of rates, one page request per day. Then mode **normal**. After that it runs by itself every 10 minutes.
5. **Check the data.** A branch named `data` appears with a `rates.json` file.
6. **Website.** On vercel.com choose *Add New → Project*, import the repo, set **Root Directory** to `site`, and deploy.
7. **Connect the two.** Edit `site/config.js` on GitHub: replace `YOUR_GITHUB_USERNAME` and `YOUR_REPO_NAME`. Vercel redeploys and the site shows live rates.
8. **Domain.** Vercel project → *Settings → Domains* → add `afn.af`, then set the DNS records Vercel shows at your domain registrar.

## Things to know

- **Vercel's free plan is for non-commercial use.** It is fine for launching and testing. Once the site earns money, Vercel's terms require the Pro plan, or you can move the `site/` folder to another host. It is plain files, so moving is easy.
- **Timing.** GitHub may run the schedule a few minutes late. The site fetches fresh data about every 5 minutes.
- **Quiet repository.** GitHub pauses scheduled workflows after 60 days with no activity. The collector's own saves normally prevent this, but check the Actions tab now and then.
- **Review file.** If a board looks wrong (for example the USD price disagrees with AED, SAR, QAR and BHD, which are tied to the dollar), it is not published. It is recorded in `review.jsonl` on the `data` branch.
- **Units.** `collector/config.py` assumes the Khorasan toman and rupee prices are per 1,000, like Sarai Shahzada's. Confirm this with the market.
- **Reference rate.** For Sarai Shahzada's USD, it is the buy/sell price that held longest between 08:00 and 15:00 Kabul time. Prices are never averaged. Daily results are saved in `daily.json`.
- **Da Afghanistan Bank.** The bank publishes cash and transfer rates with the same midpoint; the site shows the midpoint in the top card and both rates as tabs. Every day it publishes is saved in `dab_history.json`, together with the bank's average-rates table.
- **Not built yet.** A history chart, CSV download and Dari/Pashto.
- **Permission.** Tell the channel owners you use their published rates.
- **Offline test.** `python tests.py` checks the whole pipeline without internet.
