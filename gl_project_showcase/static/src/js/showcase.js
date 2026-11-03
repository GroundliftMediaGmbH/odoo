/* Minimal, dependency-free UI; Vimeo is loaded only after an explicit click. */
(function () {
  'use strict';
  document.querySelectorAll('.gl-player').forEach(function (container) {
    const button = container.querySelector('.gl-video-consent');
    if (!button) return;
    button.addEventListener('click', function () {
      const url = container.getAttribute('data-vimeo-url');
      if (!url || !/^https:\/\/(player\.vimeo\.com|vimeo\.com)\//.test(url)) return;
      const iframe = document.createElement('iframe');
      iframe.src = url;
      iframe.title = container.getAttribute('data-vimeo-title') || 'Video';
      iframe.setAttribute('allow', 'autoplay; fullscreen; picture-in-picture');
      iframe.setAttribute('allowfullscreen', '');
      iframe.setAttribute('referrerpolicy', 'strict-origin-when-cross-origin');
      iframe.setAttribute('loading', 'lazy');
      container.replaceChildren(iframe);
    });
  });
  const lightbox = document.querySelector('.gl-lightbox');
  if (!lightbox || typeof lightbox.showModal !== 'function') return;
  const image = lightbox.querySelector('.gl-lightbox-content img');
  const caption = lightbox.querySelector('.gl-lightbox-caption');
  const description = lightbox.querySelector('.gl-lightbox-description');
  const counter = lightbox.querySelector('.gl-lightbox-counter');
  const previous = lightbox.querySelector('.gl-lightbox-prev');
  const next = lightbox.querySelector('.gl-lightbox-next');
  const thumbnails = Array.from(document.querySelectorAll('.gl-lightbox-open'));
  // A photo may appear in several tagged groups. Show each photo just once when browsing.
  const seen = new Set();
  const photos = thumbnails.filter(function (button) {
    const src = button.getAttribute('data-src');
    if (!src || seen.has(src)) return false;
    seen.add(src);
    return true;
  });
  if (!photos.length) return;
  let index = 0;
  function showPhoto(position) {
    index = (position + photos.length) % photos.length;
    const button = photos[index];
    const src = button.getAttribute('data-src');
    image.src = src;
    image.alt = button.getAttribute('data-title') || '';
    caption.textContent = button.getAttribute('data-show-caption') === '1' ? (button.getAttribute('data-title') || '') : '';
    description.textContent = button.getAttribute('data-description') || '';
    counter.textContent = (index + 1) + ' / ' + photos.length;
    previous.disabled = next.disabled = photos.length <= 1;
  }
  thumbnails.forEach(function (button) {
    button.addEventListener('click', function () {
      const src = button.getAttribute('data-src');
      const photoIndex = photos.findIndex(function (photo) {
        return photo.getAttribute('data-src') === src;
      });
      if (photoIndex < 0) return;
      showPhoto(photoIndex);
      if (!lightbox.open) lightbox.showModal();
    });
  });
  previous.addEventListener('click', function () { showPhoto(index - 1); });
  next.addEventListener('click', function () { showPhoto(index + 1); });
  lightbox.addEventListener('keydown', function (event) {
    if (event.altKey || event.ctrlKey || event.metaKey || !lightbox.open) return;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      showPhoto(index + (event.key === 'ArrowRight' ? 1 : -1));
    }
  });
  lightbox.querySelector('.gl-lightbox-close').addEventListener('click', function () { lightbox.close(); });
  lightbox.addEventListener('click', function (event) { if (event.target === lightbox) lightbox.close(); });
  lightbox.addEventListener('close', function () {
    image.removeAttribute('src');
    caption.textContent = '';
    description.textContent = '';
  });
}());
