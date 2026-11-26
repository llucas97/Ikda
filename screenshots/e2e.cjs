const { chromium } = require('playwright-core');
const OUT = '/workspace/ilgeodeurim/screenshots';
const URL = 'http://127.0.0.1:8080/';
const docHtml = (title, lines) => `<html><body style="margin:0;width:800px;height:1100px;background:#fff;font-family:'Noto Sans CJK KR',sans-serif;padding:60px;box-sizing:border-box">
<h1 style="font-size:44px;border-bottom:4px solid #333">${title}</h1>${lines.map(l=>`<p style="font-size:30px">${l}</p>`).join('')}</body></html>`;

(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  // 테스트용 서류 사진 만들기
  const mk = await browser.newPage({ viewport: { width: 800, height: 1100 } });
  for (const [f, t, l] of [
    ['bill.png', '전기요금 고지서', ['청구 금액 32,400원', '납부 기한 다음 주 금요일', '고객번호 ****4521']],
    ['medicine.png', '약 봉투 · 복약 안내', ['하루 3회 식후 30분', '7일분', '행복약국']],
  ]) { await mk.setContent(docHtml(t, l)); await mk.screenshot({ path: `/tmp/imgs/${f}` }); }
  await mk.close();

  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, locale: 'ko-KR' });
  const page = await ctx.newPage();
  const apiCalls = [];
  page.on('response', r => { if (r.url().includes('/api/analyze')) apiCalls.push(r.status()); });
  page.on('console', m => { if (m.type() === 'error') console.log('console error:', m.text()); });

  const boot = async () => {
    await page.goto(URL);
    await page.waitForSelector('flt-semantics-placeholder, flutter-view', { timeout: 60000 });
    await page.waitForTimeout(2500);
    const ph = page.locator('flt-semantics-placeholder');
    if (await ph.count()) await ph.evaluate(e => e.click());
    await page.waitForTimeout(800);
  };
  const shot = async n => { await page.waitForTimeout(700); await page.screenshot({ path: `${OUT}/${n}.png` }); console.log('shot', n); };
  const upload = async file => {
    const [fc] = await Promise.all([
      page.waitForEvent('filechooser', { timeout: 15000 }),
      page.getByRole('button', { name: /서류 찍기/ }).first().click(),
    ]);
    await fc.setFiles(`/tmp/imgs/${file}`);
    await page.getByText('정리했어요').first().waitFor({ timeout: 30000 });
    await page.waitForTimeout(1200);
  };

  await boot();
  await shot('01-home-ilgeodeurim');

  // 1) 고지서: 서버 분석 결과
  await upload('bill.png');
  await shot('02-result-from-server-bill');
  // 알림 끄고 다시 켜기 → 예약 시각 안내
  await page.mouse.move(195, 500); await page.mouse.wheel(0, 500); await page.waitForTimeout(900);
  await page.getByRole('switch', { name: '하루 전 알림' }).first().click();
  await page.waitForTimeout(600);
  await page.getByRole('switch', { name: '알림 꺼짐' }).first().click();
  await page.waitForTimeout(900);
  await shot('03-remind-scheduled-snackbar');
  await page.getByRole('button', { name: /다 봤어요/ }).first().click();
  await page.waitForTimeout(1200);

  // 2) 약봉투: 좋은 모델로 올라가는 종류
  await upload('medicine.png');
  await shot('04-result-from-server-medicine');
  await page.mouse.move(195, 500); await page.mouse.wheel(0, 500); await page.waitForTimeout(900);
  await page.getByRole('switch', { name: '다 했어요' }).first().click(); // 약 할 일 완료 → 저장
  await page.waitForTimeout(800);
  await page.getByRole('button', { name: /다 봤어요/ }).first().click();
  await page.waitForTimeout(1200);
  await shot('05-home-after-two-docs');

  // 3) 새로고침 → 저장된 서류·완료 상태 유지 확인
  const stored = await page.evaluate(() => localStorage.getItem('flutter.ilgeodeurim.documents.v1'));
  await boot();
  await shot('06-home-after-reload');
  const docs = JSON.parse(JSON.parse(stored));
  console.log('stored docs:', docs.map(d => `${d.docType}:${d.title}:done=${d.todos.map(t => t.done).join('/')}:amount=${d.amount}:due=${d.dueDate}`));
  console.log('api statuses:', apiCalls);
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
