// SVGから透過PNGおよびプレビューPNGをレンダリングする。
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

// 通常のNode.jsモジュール探索を使う。別の配置ならNODE_PATHで指定できる。
let playwright;
try {
  playwright = require('playwright');
} catch (error) {
  console.error('Playwrightが見つかりません。再生成用の環境にインストールしてください。');
  process.exit(1);
}

const { chromium } = playwright;

(async () => {
  const root = path.resolve(__dirname, '..');
  const positional = process.argv.slice(2).filter(arg => arg !== '--all');
  const targetDir = positional[0]
    ? path.resolve(positional[0])
    : path.join(root, 'templates', 'manga-project', 'templates', 'panel-templates');

  const catalogPath = path.join(targetDir, 'catalog.json');
  if (!fs.existsSync(catalogPath)) {
    console.error('カタログが見つかりません:', catalogPath);
    process.exit(1);
  }
  const data = JSON.parse(fs.readFileSync(catalogPath, 'utf8'));

  const launchOptions = { headless: true };
  const winProg = process.env['ProgramFiles'] || process.env['ProgramFiles(x86)'];
  if (winProg) {
    const candidate = path.join(winProg, 'Google', 'Chrome', 'Application', 'chrome.exe');
    if (fs.existsSync(candidate)) {
      launchOptions.executablePath = candidate;
    }
  }

  const browser = await chromium.launch(launchOptions);

  const page = await browser.newPage({
    viewport: { width: 1000, height: 1500 },
    deviceScaleFactor: 2
  });

  const forceAll = process.argv.includes('--all');
  let renderedCount = 0;

  for (const t of data.templates) {
    const transPath = path.join(targetDir, t.assets.transparentPng);
    const prevPath = path.join(targetDir, t.assets.previewPng);

    const needTrans = forceAll || !fs.existsSync(transPath);
    const needPrev = forceAll || !fs.existsSync(prevPath);

    if (needTrans) {
      const svgUrl = pathToFileURL(path.join(targetDir, t.assets.svg)).href;
      await page.goto(svgUrl);
      await page.screenshot({ path: transPath, omitBackground: true });
      renderedCount++;
    }

    if (needPrev) {
      const guideUrl = pathToFileURL(path.join(targetDir, t.assets.guideSvg)).href;
      await page.goto(guideUrl);
      await page.screenshot({ path: prevPath });
      renderedCount++;
    }
  }

  await page.close();
  await browser.close();

  console.log(JSON.stringify({
    templates: data.templateCount,
    renderedScreenshots: renderedCount,
    targetDirectory: targetDir
  }));
})().catch(err => {
  console.error(err);
  process.exit(1);
});
