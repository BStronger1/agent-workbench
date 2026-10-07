export class ContractError extends Error {}

async function uniqueTarget(page, id, action) {
  const locator = page.getByTestId(id);
  if (await locator.count() === 0) {
    try { await locator.waitFor({state:'attached',timeout:2000}); } catch {}
  }
  const count = await locator.count();
  if (count !== 1) throw new ContractError(`Target ${id} must match exactly one element before ${action}; found ${count}. Keep this data-testid only on the intended element; use distinct IDs for other list items.`);
  return locator;
}

export async function executeSteps(page, steps) {
  if (!Array.isArray(steps) || steps.length > 12) throw new ContractError('Invalid step count');
  const before = new Map();
  for (const step of steps) {
    if (!/^[a-zA-Z0-9_-]{1,64}$/.test(step.target) || !['check','fill','click','assert_text','assert_changed'].includes(step.action)) throw new ContractError('Invalid operation');
    if (step.action === 'assert_changed') {
      const target = await uniqueTarget(page, step.target, 'change baseline');
      before.set(step.target, (await target.textContent())?.trim());
    }
  }
  for (const step of steps) {
    const target = await uniqueTarget(page, step.target, step.action);
    try {
      if (step.action === 'check') await target.check();
      if (step.action === 'fill') await target.fill(step.value ?? '');
      if (step.action === 'click') await target.click();
      if (step.action.startsWith('assert_')) {
        if (!(await target.isVisible())) throw new ContractError(`Result not visible: ${step.target}`);
        try {
          await page.waitForFunction(({id, expected, prior, action}) => {
            const matches = document.querySelectorAll(`[data-testid="${id}"]`);
            if (matches.length !== 1) return false;
            const text = matches[0].textContent?.trim();
            return action === 'assert_text' ? text === expected : text !== undefined && text !== prior;
          }, {id:step.target, expected:step.value, prior:before.get(step.target), action:step.action}, {timeout:2000});
        } catch {
          const current = await uniqueTarget(page, step.target, step.action);
          const actual = (await current.textContent())?.trim().slice(0,200);
          const expectation = step.action === 'assert_text' ? `exact text ${JSON.stringify(step.value)}` : `text changed from ${JSON.stringify(before.get(step.target)?.slice(0,200))}`;
          throw new ContractError(`Assertion ${step.target} failed: expected ${expectation}; got ${JSON.stringify(actual)}.`);
        }
      }
    } catch (error) {
      if (error instanceof ContractError) throw error;
      // Do not expose Playwright stack traces or arbitrary page call logs.
      throw new ContractError(`Action ${step.action} on unique target ${step.target} could not be completed. Check the element type, visibility and interaction handler.`);
    }
  }
}