/* ==========================================================================
   MODULE: Protect Yourself Knowledge Hub & Article Router
   ========================================================================== */

import { BLOG_POSTS } from '../blog-data.js?v=1.1';

export function initBlogHub() {
  const blogGrid = document.getElementById('blog-posts-grid');
  const searchInput = document.getElementById('blog-search-input');
  const tagBtns = document.querySelectorAll('.blog-filter-tag');

  if (!blogGrid || !BLOG_POSTS) return;

  function renderPosts(posts) {
    blogGrid.innerHTML = '';
    if (posts.length === 0) {
      blogGrid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--white-muted); padding: 3rem;">No legal articles matching your query.</div>`;
      return;
    }

    posts.forEach(post => {
      const card = document.createElement('div');
      card.className = 'glass-panel blog-card tri-border-card';
      card.innerHTML = `
        <div>
          <div class="blog-tag">${post.tag} • ${post.category}</div>
          <h3 class="blog-card-title">${post.title}</h3>
          <p class="blog-excerpt">${post.excerpt}</p>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 1rem;">
          <span style="font-size: 0.78rem; color: var(--white-muted);">${post.readTime}</span>
          <span class="read-more-link">Read Full Guide &rarr;</span>
        </div>
      `;

      card.addEventListener('click', () => {
        window.location.hash = `#blog/${post.id}`;
      });
      blogGrid.appendChild(card);
    });
  }

  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase();
      const filtered = BLOG_POSTS.filter(p =>
        p.title.toLowerCase().includes(q) ||
        p.excerpt.toLowerCase().includes(q) ||
        p.category.toLowerCase().includes(q) ||
        p.tag.toLowerCase().includes(q)
      );
      renderPosts(filtered);
    });
  }

  tagBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tagBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const tag = btn.getAttribute('data-tag');
      if (tag === 'all') {
        renderPosts(BLOG_POSTS);
      } else {
        renderPosts(BLOG_POSTS.filter(p => p.category.toLowerCase() === tag.toLowerCase() || p.tag.toLowerCase() === tag.toLowerCase()));
      }
    });
  });

  renderPosts(BLOG_POSTS);
}
