const { chromium } = require('/usr/local/lib/pnpm/5/.pnpm/playwright-core@1.59.1/node_modules/playwright-core');
const OUT = '/workspace/ilg_12a6550/shots';
const URL = 'http://127.0.0.1:8096/?v=12a6550';

async function labelsOf(page) {
  return page.evaluate(() => [...document.querySelectorAll('[aria-label]')].map(n => n.getAttribute('aria-label')));
}
async function shot(page, name) {
  const path = `${OUT}/${name}.png`;
  await page.screenshot({ path });
  console.log('SHOT', name, (await labelsOf(page)).slice(0, 12));
}
async function enableSem(page) {
  const ph = page.locator('flt-semantics-placeholder');
  if (await ph.count()) {
    await ph.evaluate(e => e.click());
    await page.waitForTimeout(1200);
    console.log('semantics on');
  }
}
async function clickRole(page, name, ms = 5000) {
  const loc = page.getByRole('button', { name });
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (await loc.count()) { await loc.first().click(); await page.waitForTimeout(700); return true; }
    await page.waitForTimeout(200);
  }
  console.log('MISS role', String(name));
  return false;
}
async function clickText(page, text, ms = 4000) {
  const loc = page.getByText(text, { exact: true });
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (await loc.count()) { await loc.first().click(); await page.waitForTimeout(700); return true; }
    await page.waitForTimeout(200);
  }
  console.log('MISS text', text);
  return false;
}
async function goBack(page) {
  if (await clickRole(page, /뒤로|Back/, 800)) return;
  await page.mouse.click(28, 48);
  await page.waitForTimeout(900);
}
async function waitHome(page) {
  for (let i = 0; i < 25; i++) {
    const labs = await labelsOf(page);
    if (labs.includes('읽다') || labs.includes('계정') || await page.getByRole('button', { name: '가족' }).count() || await page.getByRole('button', { name: '계정' }).count()) return;
    await page.waitForTimeout(300);
  }
}

async function boot(browser, path='/?v=12a6550') {
  const ctx = await browser.newContext({
    viewport: { width: 412, height: 915 },
    deviceScaleFactor: 2,
    locale: 'ko-KR',
    serviceWorkers: 'block',
  });
  const page = await ctx.newPage();
  page.on('pageerror', e => console.log('pageerror', e.message));
  await page.goto('http://127.0.0.1:8096' + path, { waitUntil: 'networkidle' });
  await page.waitForSelector('flutter-view, canvas, flt-glass-pane', { timeout: 60000 });
  await page.waitForTimeout(3500);
  await enableSem(page);
  return { ctx, page };
}

(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });

  // ---------- skipped login / account prompt ----------
  {
    const { ctx, page } = await boot(browser, '/?v=skip');
    await shot(page, '01-login');
    if (!(await clickRole(page, '나중에 할게요') || await clickText(page, '나중에 할게요'))) {
      await page.mouse.click(206, 780);
      await page.waitForTimeout(1000);
    }
    await waitHome(page);
    await shot(page, '02-home-skipped');
    if (await clickRole(page, '계정')) {
      await page.waitForTimeout(800);
      await shot(page, '03-account-logged-out');
      await page.keyboard.press('Escape');
      await page.waitForTimeout(500);
    }
    await ctx.close();
  }

  // ---------- main signed-in flow ----------
  const { ctx, page } = await boot(browser, '/?v=main');
  await shot(page, '04-login-again');
  if (!(await clickRole(page, /카카오/))) await page.mouse.click(206, 520);
  await waitHome(page);
  await page.waitForTimeout(800);
  await shot(page, '05-home');
  await page.mouse.wheel(0, 650);
  await page.waitForTimeout(500);
  await shot(page, '06-home-scrolled');

  // account + dialogs
  if (await clickRole(page, '계정')) {
    await page.waitForTimeout(800);
    await shot(page, '07-account-signed-in');
    if (await clickRole(page, '로그아웃') || await clickText(page, '로그아웃')) {
      await page.waitForTimeout(600);
      await shot(page, '08-account-logout-confirm');
      await clickRole(page, '아니요') || await clickText(page, '아니요');
      await page.waitForTimeout(400);
      if (!(await page.getByRole('button', { name: '로그아웃' }).count())) {
        await clickRole(page, '계정');
        await page.waitForTimeout(500);
      }
    }
    if (await clickRole(page, '회원 탈퇴') || await clickText(page, '회원 탈퇴')) {
      await page.waitForTimeout(600);
      await shot(page, '09-account-withdraw-confirm');
      await clickRole(page, '아니요') || await clickText(page, '아니요');
      await page.waitForTimeout(400);
    }
    await page.keyboard.press('Escape');
    await page.waitForTimeout(600);
  }

  // family-sent hospital (자녀가 보냄)
  await page.mouse.wheel(0, 200);
  await page.waitForTimeout(300);
  if (!(await clickText(page, '건강검진 안내'))) {
    await page.mouse.click(206, 720);
    await page.waitForTimeout(1000);
  }
  await page.waitForTimeout(800);
  await shot(page, '10-result-family-sent');
  await page.mouse.wheel(0, 500);
  await page.waitForTimeout(400);
  await shot(page, '11-result-family-sent-scrolled');
  if (await clickText(page, '자세히 보기') || await clickRole(page, /자세히/)) {
    await page.waitForTimeout(500);
    await page.mouse.wheel(0, 300);
    await shot(page, '12-result-family-sent-details');
  }
  await goBack(page);

  // bill result
  await page.mouse.wheel(0, 700);
  await page.waitForTimeout(400);
  if (!(await clickText(page, '한국전력 전기요금 고지서'))) {
    // try 지난 서류 / 전기요금 내기
    if (!(await clickText(page, '전기요금 내기'))) await page.mouse.click(206, 820);
    await page.waitForTimeout(1000);
  }
  await page.waitForTimeout(800);
  await shot(page, '13-result-bill');
  if (await clickRole(page, '지우기') || await clickText(page, '지우기')) {
    await page.waitForTimeout(600);
    await shot(page, '14-result-delete-dialog');
    await clickRole(page, '그대로 두기') || await clickText(page, '그대로 두기');
    await page.waitForTimeout(400);
  }
  await goBack(page);

  // 챙길 일
  await page.mouse.wheel(0, 400);
  await page.waitForTimeout(300);
  if (!(await clickRole(page, /전체/) || await clickText(page, '전체'))) {
    // section more may be unlabeled; try right side of 챙길 일
  }
  // If still on home, click 챙길 일 more via text nearby
  if (await page.getByRole('button', { name: '가족' }).count()) {
    // try heading more - click "챙길 일" row right
    const stillHome = true;
    if (stillHome) {
      // scroll and click the 전체 chevron if present
      if (!(await clickText(page, '챙길 일'))) {
        // already visible maybe
      }
    }
  }
  // explicit: look for 전체
  if (await clickText(page, '전체') || await clickRole(page, '전체')) {
    await page.waitForTimeout(700);
    await shot(page, '15-todos');
    await goBack(page);
  }

  // history — 지난 서류 more
  await page.mouse.wheel(0, 800);
  await page.waitForTimeout(400);
  if (await clickText(page, '지난 서류')) {
    // might need the more control; try 전체 again
    if (await clickRole(page, '전체') || await clickText(page, '전체')) {
      await page.waitForTimeout(700);
      await shot(page, '16-history');
      await goBack(page);
    } else {
      // maybe clicked header only; try again at right
      await page.mouse.click(380, 780);
      await page.waitForTimeout(800);
      await shot(page, '16-history');
      const labs = (await labelsOf(page)).join();
      if (labs.includes('읽다') || labs.includes('지난 서류') && await page.getByRole('button', { name: '가족' }).count()) {
        // still home, keep shot anyway if it looks like history from later read
      }
      if (await page.getByRole('button', { name: '가족' }).count() === 0) await goBack(page);
    }
  }

  // 우리 가족 tree
  if (!(await clickRole(page, '가족'))) await page.mouse.click(380, 40);
  await page.waitForTimeout(900);
  await shot(page, '17-family-tree');
  await page.mouse.wheel(0, 500);
  await page.waitForTimeout(400);
  await shot(page, '18-family-tree-scrolled');

  // 별명·관계 바꾸기
  if (await clickRole(page, '별명·관계 바꾸기') || await clickText(page, '별명·관계 바꾸기')) {
    await page.waitForTimeout(800);
    await shot(page, '19-edit-relation-sheet');
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
  }

  // 권한
  if (await clickRole(page, '권한') || await clickText(page, '권한')) {
    await page.waitForTimeout(800);
    await shot(page, '20-family-permission');
    await goBack(page);
  }

  // 연결 끊기 dialog
  if (await clickRole(page, '연결 끊기') || await clickText(page, '연결 끊기')) {
    await page.waitForTimeout(600);
    await shot(page, '21-unlink-confirm');
    await clickRole(page, '아니요') || await clickText(page, '아니요');
    await page.waitForTimeout(400);
  }

  // join
  if (await clickRole(page, '번호 넣기') || await clickText(page, '번호 넣기')) {
    await page.waitForTimeout(800);
    await shot(page, '22-join');
    // type 123456
    for (const d of ['1','2','3','4','5','6']) {
      if (!(await clickRole(page, d) || await clickText(page, d))) {
        // keypad coordinates: 3-col bottom area
      }
    }
    await page.waitForTimeout(1000);
    await shot(page, '23-join-preview');
    await goBack(page);
  }

  // invite flow
  if (await clickRole(page, '가족 초대하기') || await clickText(page, '가족 초대하기')) {
    await page.waitForTimeout(700);
    await shot(page, '24-invite-role-sheet');
    if (await clickRole(page, '나는 부모예요') || await clickText(page, '나는 부모예요')) {
      await page.waitForTimeout(800);
      await shot(page, '25-relation-step1');
      if (await clickRole(page, '딸') || await clickText(page, '딸')) {
        await page.mouse.wheel(0, 400);
        await page.waitForTimeout(300);
        if (await clickRole(page, '다음') || await clickText(page, '다음')) {
          await page.waitForTimeout(800);
          await shot(page, '26-relation-step2');
          if (await clickRole(page, '어머니') || await clickText(page, '어머니')) {
            await page.mouse.wheel(0, 400);
          }
          if (await clickRole(page, '번호 만들기') || await clickText(page, '번호 만들기')) {
            await page.waitForTimeout(900);
            await shot(page, '27-invite-code');
          }
        }
      }
    }
    // back to family
    for (let i = 0; i < 5; i++) {
      if (await page.getByText('우리 가족', { exact: true }).count() && await page.getByRole('button', { name: '가족 초대하기' }).count()) break;
      await goBack(page);
      await page.waitForTimeout(300);
    }
  }

  // empty family via unlink both
  for (let n = 0; n < 2; n++) {
    if (await clickRole(page, '연결 끊기') || await clickText(page, '연결 끊기')) {
      await page.waitForTimeout(400);
      await clickRole(page, '끊기') || await clickText(page, '끊기');
      await page.waitForTimeout(700);
    }
  }
  await shot(page, '28-family-empty');

  // gallery: retake then analyzing
  await goBack(page);
  await page.waitForTimeout(600);
  if (await clickRole(page, '사진첩에서 고르기') || await clickText(page, '사진첩에서 고르기')) {
    await page.waitForTimeout(800);
    const input = page.locator('input[type=file]');
    if (await input.count()) {
      await input.first().setInputFiles('/tmp/tiny_dark.jpg');
      await page.waitForTimeout(2000);
      await shot(page, '29-retake');
      // send anyway to reach owner/analyzing
      if (await clickRole(page, '그래도 보내기') || await clickText(page, '그래도 보내기')) {
        await page.waitForTimeout(800);
        await shot(page, '30-owner-or-analyzing');
        // if owner sheet, pick 내 서류
        if (await clickRole(page, '내 서류') || await clickText(page, '내 서류')) {
          await page.waitForTimeout(400);
          await shot(page, '31-analyzing');
          await page.waitForTimeout(3500);
          await shot(page, '32-after-analyze');
        } else {
          // maybe already analyzing
          await page.waitForTimeout(1500);
          await shot(page, '31-analyzing');
          await page.waitForTimeout(3000);
          await shot(page, '32-after-analyze');
        }
      }
    } else {
      console.log('no file input for gallery');
      await shot(page, '29-gallery-no-input');
    }
  }

  await ctx.close();
  await browser.close();
  console.log('DONE');
})().catch(e => { console.error(e); process.exit(1); });
