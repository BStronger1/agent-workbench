export async function executeSteps(page, steps) {
  if (!Array.isArray(steps) || steps.length > 12) throw new Error('Invalid step count');
  const before = new Map();
  for (const step of steps) {
    if (!/^[a-zA-Z0-9_-]{1,64}$/.test(step.target) || !['check','fill','click','assert_text','assert_changed'].includes(step.action)) throw new Error('Invalid operation');
    if (step.action === 'assert_changed') before.set(step.target, (await page.getByTestId(step.target).textContent())?.trim());
  }
  for (const step of steps) {
    const target = page.getByTestId(step.target);
    if (step.action === 'check') await target.check();
    if (step.action === 'fill') await target.fill(step.value ?? '');
    if (step.action === 'click') await target.click();
    if (step.action.startsWith('assert_')) {
      if (!(await target.isVisible())) throw new Error(`Result not visible: ${step.target}`);
      await page.waitForFunction(({id, expected, prior, action}) => {
        const text = document.querySelector(`[data-testid="${id}"]`)?.textContent?.trim();
        return action === 'assert_text' ? text?.trim() === expected : text !== undefined && text !== prior;
      }, {id: step.target, expected: step.value, prior: before.get(step.target), action: step.action}, {timeout: 2000});
    }
  }
}