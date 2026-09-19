/* Local presentation only; all purchasing and authorization remain server-side. */
(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduceMotion) {
    document.documentElement.classList.add("motion-ready");
    const revealTargets = document.querySelectorAll(
      ".market-hero, .category-strip, .home-section, .product-card, .trainer-card, .purchase-order, .trainer-profile-hero"
    );
    revealTargets.forEach((element, index) => {
      element.classList.add("reveal-pending");
      element.style.setProperty("--reveal-delay", String(Math.min(index % 4, 3) * 55) + "ms");
    });
    if ("IntersectionObserver" in window) {
      const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      }, { threshold: 0.08, rootMargin: "0px 0px -24px" });
      revealTargets.forEach(element => observer.observe(element));
    } else {
      revealTargets.forEach(element => element.classList.add("is-visible"));
    }
  }

  document.querySelector("[data-sort]")?.addEventListener("change", event => event.target.form.requestSubmit());
  document.querySelectorAll('nav a').forEach(link => {
    if (link.getAttribute("href") === window.location.pathname) link.setAttribute("aria-current", "page");
  });
  const editor = document.querySelector(".product-editor");
  if (!editor) return;
  const preview = document.querySelector(".preview-panel");
  const sync = () => {
    preview.querySelectorAll("[data-preview]").forEach(target => {
      const key = target.dataset.preview;
      const input = editor.elements.namedItem(key);
      if (!input) return;
      let value = input.tagName === "SELECT" ? input.selectedOptions[0]?.textContent : input.value;
      if (key === "price") value = "₩" + (Number(input.value) || 0).toLocaleString("ko-KR");
      if (key === "duration_weeks" && value) value += "주";
      if (key === "sessions_per_week" && value) value = "주 " + value + "회";
      target.textContent = value || ({title:"운동 루틴 상품명",description:"프로그램의 구성과 운동 목표를 소개해 주세요."}[key] || "선택 전");
    });
  };
  editor.addEventListener("input", sync);
  editor.addEventListener("change", sync);
  let objectURL;
  editor.elements.namedItem("thumbnail_file")?.addEventListener("change", event => {
    const file = event.target.files[0];
    if (!file || !["image/jpeg", "image/png", "image/webp"].includes(file.type)) return;
    if (objectURL) URL.revokeObjectURL(objectURL);
    objectURL = URL.createObjectURL(file);
    const image = preview.querySelector("[data-preview-image]");
    image.src = objectURL;
    image.hidden = false;
    preview.querySelector("[data-preview-placeholder]")?.setAttribute("hidden", "");
  });
  editor.elements.namedItem("routine_file")?.addEventListener("change", event => {
    const file = event.target.files[0];
    preview.querySelector("[data-file-name]").textContent = file ? file.name + " · " + (file.size / 1024 / 1024).toFixed(1) + " MB" : "";
  });
  editor.elements.namedItem("detail_images")?.addEventListener("change", event => {
    const count = event.target.files.length;
    const label = preview.querySelector("[data-detail-file-count]");
    if (label) label.textContent = count ? `상세 이미지 ${count}장 선택됨` : "";
  });
  window.addEventListener("pagehide", () => { if (objectURL) URL.revokeObjectURL(objectURL); });
  sync();
})();
