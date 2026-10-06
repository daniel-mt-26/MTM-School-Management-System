// Whole-unit native arrows, while retaining cents and every other native constraint.
export function validateMoneyForm(form) {
  const amounts = [...form.querySelectorAll('input[type="number"][step="1"]')]
  amounts.forEach((input) => { input.step = 'any' })
  const valid = form.reportValidity()
  amounts.forEach((input) => { input.step = '1' })
  return valid
}
