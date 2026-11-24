/* Playwright MCP function. Open a local Frappe host fixture running the real
 * supply_planning controller first. No customer data or deployment operations. */
async (page) => {
  const url = page.url(), results = [], errors = [];
  const check = (value, message) => { if (!value) errors.push(message); };
  const surface = () => page.locator('.supply-planning-surface');
  const local = selector => surface().locator(selector);
  const settle = () => page.evaluate(() => new Promise(resolve =>
    requestAnimationFrame(() => requestAnimationFrame(resolve))));
  // Half-sized CSS viewports cover the layout space at 200% page zoom; the
  // browser toolbar zoom is not changed by this headless test.
  for (const [width,height] of [[1440,900],[1024,900],[900,900],[768,1024],[360,800],
    [720,450],[512,450],[450,450],[384,512],[180,400]]) {
    await page.setViewportSize({width,height});
    await page.goto(url);
    await local('#wb-rows [data-row]').first().waitFor();
    await settle();
    const geometry = await surface().evaluate(el => {
      const d = el.shadowRoot, b = d.querySelector('#board-scroll'), r = b.getBoundingClientRect();
      return {height:innerHeight, root:document.documentElement.scrollHeight,
        width:innerWidth, rootWidth:document.documentElement.scrollWidth,
        bottom:el.getBoundingClientRect().bottom,
        chrome:d.querySelector('#workspace').getBoundingClientRect().top-el.getBoundingClientRect().top,
        rows:[...d.querySelectorAll('#wb-rows tr')].filter(row => {
          const x=row.getBoundingClientRect(); return x.top>=r.top && x.bottom<=r.bottom;
        }).length};
    });
    check(geometry.root<=height+1 && geometry.rootWidth<=width+1 && Math.abs(geometry.bottom-height)<=1,
      `${width}: host overflow`);
    check(await page.locator('iframe').count()===0, `${width}: unexpected iframe`);
    if (width>=768) {
      check(geometry.chrome<=140, `${width}: chrome too tall`);
      check(geometry.rows>=8, `${width}: fewer than eight visible rows`);
    }
    await page.evaluate(() => {
      const canary=document.createElement('div'); canary.id='wb-rows'; canary.hidden=true;
      canary.textContent='host-canary'; document.body.appendChild(canary);
    });
    await local('[data-set="base"]').click();
    await local('#wb-rows [data-row]').first().focus();
    await page.keyboard.press('Enter');
    await local('.detail-anchors [data-anchor="detail-actions"]').click();
    const form = await surface().evaluate(el => {
      const d=el.shadowRoot, panel=d.querySelector('#detail-actions').getBoundingClientRect();
      const submit=d.querySelector('#wb-submit').getBoundingClientRect();
      return {visible:submit.top>=panel.top && submit.bottom<=Math.min(panel.bottom,innerHeight)+1,
        panelHeight:panel.height, focus:d.activeElement.id};
    });
    check(form.visible && form.panelHeight>0, `${width}: operations submit unreachable`);
    check(form.focus==='detail-actions', `${width}: segment focus lost`);
    for (const id of ['wb-reason','wb-evidence']) {
      await local('#'+id).focus();
      const exposed = await surface().evaluate((el,id) => {
        const d=el.shadowRoot, target=d.getElementById(id).getBoundingClientRect();
        const panel=d.querySelector('#detail-actions').getBoundingClientRect();
        const footer=d.querySelector('.submitline').getBoundingClientRect();
        return target.top>=panel.top-1 && target.bottom<=footer.top+1 && document.documentElement.scrollTop===0;
      }, id);
      check(exposed, `${width}: ${id} focus hidden behind sticky submit`);
    }
    check(await page.locator('body > #wb-rows').textContent()==='host-canary', `${width}: shadow code touched host`);
    if (await local('#detail-sheet').evaluate(e=>e.open)) {
      await page.keyboard.press('Escape');
      check(await local('#wb-rows [aria-current=true]').evaluate(e=>e===e.getRootNode().activeElement),
        `${width}: drawer did not restore row focus`);
    }
    for (const view of ['evidence','analysis','method']) {
      await local(`[data-view="${view}"]`).click();
      const state = await surface().evaluate(el => {
        const d=el.shadowRoot;
        return {overflow:document.documentElement.scrollHeight>innerHeight+1,
          areas:[...d.querySelectorAll('.view.active *')].filter(e => e.clientHeight>0 &&
            e.scrollHeight>e.clientHeight+1 && ['auto','scroll'].includes(getComputedStyle(e).overflowY)).length};
      });
      check(!state.overflow && state.areas<=2, `${width}: ${view} scroll ownership`);
    }
    results.push({width,height,geometry,form});
  }
  await page.setViewportSize({width:1440,height:900}); await page.goto(url);
  await local('#wb-rows [data-row]').first().click();
  // Expand from the default summary, then the evidence segment owns right scroll.
  await local('.detail-anchors [data-anchor="detail-summary"]').click();
  await local('[data-expand-evidence]').first().click();
  const positions = () => surface().evaluate(el => {
    const d=el.shadowRoot;
    return {board:d.querySelector('#board-scroll').scrollTop,detail:d.querySelector('#detail-evidence').scrollTop,
      root:document.documentElement.scrollTop,head:d.querySelector('.detail-head').getBoundingClientRect().top};
  });
  const initial=await positions();
  await local('#board-scroll').hover(); await page.mouse.wheel(0,450); await page.waitForTimeout(100);
  const left=await positions();
  check(left.board>initial.board && left.detail===initial.detail && left.root===0, 'left wheel crossed panes');
  await local('#detail-evidence').hover(); await page.mouse.wheel(0,450); await page.waitForTimeout(100);
  const right=await positions();
  check(right.detail>left.detail && right.board===left.board && right.root===0 && right.head===left.head,
    'right wheel crossed panes or moved its header');
  await local('.detail-anchors [data-anchor="detail-evidence"]').focus();
  await page.keyboard.press('ArrowRight');
  check(await local('.detail-anchors [data-anchor="detail-actions"]').getAttribute('aria-selected')==='true',
    'detail tab keyboard navigation failed');
  // Header reflow must resize the existing surface without another data fetch.
  const handle=await surface().elementHandle();
  await page.evaluate(() => {document.querySelector('.page-head').style.height='82px';});
  await settle(); await settle();
  check(await surface().evaluate(e=>Math.abs(e.getBoundingClientRect().bottom-innerHeight)<=1), 'host header reflow');
  check(await handle.evaluate(e=>e===document.querySelector('.supply-planning-surface')), 'resize rebuilt content');
  await page.evaluate(() => {window.route='another-page';window.handlers.forEach(fn=>fn());});
  check(await page.locator('.supply-fit').count()===0, 'route exit left height locks');
  await page.evaluate(() => {window.route='supply-planning';window.handlers.forEach(fn=>fn());});
  await settle();
  check(await page.locator('.supply-fit').count()>0, 'route return did not restore height locks');
  return {results,wheel:{initial,left,right},errors};
}
