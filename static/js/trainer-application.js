(() => {
  const forms = document.querySelector("[data-certification-forms]");
  const template = document.querySelector("[data-certification-template]");
  const addButton = document.querySelector("[data-add-certification]");
  const totalInput = document.querySelector("[name='certifications-TOTAL_FORMS']");
  const maxInput = document.querySelector("[name='certifications-MAX_NUM_FORMS']");
  if (!forms || !template || !addButton || !totalInput) return;

  const maxForms = Number(maxInput?.value) || 5;
  const updateState = () => {
    const currentForms = forms.querySelectorAll("[data-certification-form]");
    addButton.disabled = currentForms.length >= maxForms;
    addButton.textContent = addButton.disabled ? "최대 5개까지 등록 가능" : "＋ 자격증 추가";
  };

  addButton.addEventListener("click", () => {
    const index = Number(totalInput.value);
    if (index >= maxForms) return;
    forms.insertAdjacentHTML("beforeend", template.innerHTML.replaceAll("__prefix__", String(index)));
    totalInput.value = String(index + 1);
    updateState();
    forms.lastElementChild?.querySelector("input")?.focus();
  });

  updateState();
})();
