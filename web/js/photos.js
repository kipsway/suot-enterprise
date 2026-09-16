/* SUOT Neo — работа с фото: загрузка, превью, лайтбокс */
(function () {
  const MAX_MB = 8;
  const OK_TYPES = /^image\/(png|jpe?g|webp|gif|bmp)$/i;

  function isImage(file) {
    return file && OK_TYPES.test(file.type);
  }

  async function upload(file) {
    if (!isImage(file))
      throw new Error(I18N.t("dz.wrong"));
    if (file.size > MAX_MB * 1024 * 1024)
      throw new Error(I18N.t("dz.wrong"));
    const res = await API.upload(file);
    return res.url;
  }

  /* Открытие полноэкранного просмотра */
  function lightbox(src) {
    document.dispatchEvent(new CustomEvent("suot-lightbox",
      { detail: { src }, bubbles: true }));
  }

  window.Photos = { isImage, upload, lightbox, MAX_MB };
})();
