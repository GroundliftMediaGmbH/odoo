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
  const image = lightbox.querySelector('img');
  const caption = lightbox.querySelector('p');
  document.querySelectorAll('.gl-lightbox-open').forEach(function (button) {
    button.addEventListener('click', function () {
      image.src = button.getAttribute('data-src');
      image.alt = button.getAttribute('data-title') || '';
      caption.textContent = button.getAttribute('data-show-caption') === '1' ? (button.getAttribute('data-title') || '') : '';
      lightbox.showModal();
    });
  });
  lightbox.querySelector('.gl-lightbox-close').addEventListener('click', function () { lightbox.close(); });
  lightbox.addEventListener('click', function (event) { if (event.target === lightbox) lightbox.close(); });
  lightbox.addEventListener('close', function () { image.removeAttribute('src'); });
}());
