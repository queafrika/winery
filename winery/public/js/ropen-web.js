/* =============================================================================
   Ropen storefront front-end.
   No framework, no build step — this file is served straight from /assets.

   The cart lives in localStorage so guest pages stay fully cacheable; the
   server re-prices it on every render and again at checkout, so nothing here
   is trusted for money.
   ========================================================================== */
(function () {
  'use strict';

  var CART_KEY = 'ropen.cart.v1';
  var MAX_QTY = 60;

  /* ── tiny helpers ──────────────────────────────────────────────────── */
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function call(method, args) {
    var token = (document.documentElement.dataset.csrf || '').trim();
    var headers = { 'Content-Type': 'application/json', 'X-Frappe-Site-Name': location.hostname };
    if (token && token !== 'None') headers['X-Frappe-CSRF-Token'] = token;

    return fetch('/api/method/' + method, {
      method: 'POST',
      headers: headers,
      credentials: 'same-origin',
      body: JSON.stringify(args || {})
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          if (!res.ok) {
            throw new Error(serverMessage(body) || 'Something went wrong. Please try again.');
          }
          return body.message;
        });
      });
  }

  // Frappe returns errors as a JSON-encoded list in _server_messages.
  function serverMessage(body) {
    try {
      var msgs = JSON.parse(body._server_messages || '[]');
      if (msgs.length) {
        var first = JSON.parse(msgs[0]);
        return String(first.message || '').replace(/<[^>]+>/g, '');
      }
    } catch (e) { /* fall through */ }
    if (body.exception) return String(body.exception).split(':').slice(1).join(':').trim();
    return '';
  }


  /* Mirrors templates/ropen/icons.html for the states rendered client-side. */
  var ICON_PATHS = {
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    cart: '<circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/>' +
          '<path d="M1 1h4l2.7 13.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H6"/>'
  };

  function svgIcon(name, size) {
    return '<svg class="icon" viewBox="0 0 24 24" width="' + (size || 22) + '" height="' +
      (size || 22) + '" fill="none" stroke="currentColor" stroke-width="1.7" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      (ICON_PATHS[name] || '') + '</svg>';
  }

  /* ── toasts ────────────────────────────────────────────────────────── */
  function toast(message, kind) {
    var host = $('.toast-host');
    if (!host) {
      host = document.createElement('div');
      host.className = 'toast-host';
      host.setAttribute('role', 'status');
      host.setAttribute('aria-live', 'polite');
      document.body.appendChild(host);
    }
    var el = document.createElement('div');
    el.className = 'toast' + (kind ? ' toast-' + kind : '');
    el.textContent = message;
    host.appendChild(el);
    setTimeout(function () {
      el.classList.add('is-out');
      setTimeout(function () { el.remove(); }, 250);
    }, 3200);
  }

  /* ── cart store ────────────────────────────────────────────────────── */
  var Cart = {
    read: function () {
      try {
        var raw = JSON.parse(localStorage.getItem(CART_KEY) || '[]');
        if (!Array.isArray(raw)) return [];
        return raw
          .filter(function (l) { return l && l.item_code && Number(l.qty) > 0; })
          .map(function (l) {
            return { item_code: String(l.item_code), qty: Math.min(MAX_QTY, Math.floor(Number(l.qty))) };
          });
      } catch (e) {
        return [];
      }
    },

    write: function (lines) {
      try {
        localStorage.setItem(CART_KEY, JSON.stringify(lines));
      } catch (e) { /* private mode — cart is session-only, nothing to do */ }
      this.broadcast();
    },

    add: function (itemCode, qty) {
      var lines = this.read();
      var found = lines.filter(function (l) { return l.item_code === itemCode; })[0];
      qty = Math.max(1, Math.floor(Number(qty) || 1));

      if (found) {
        found.qty = Math.min(MAX_QTY, found.qty + qty);
      } else {
        lines.push({ item_code: itemCode, qty: Math.min(MAX_QTY, qty) });
      }
      this.write(lines);
      return lines;
    },

    setQty: function (itemCode, qty) {
      qty = Math.floor(Number(qty) || 0);
      var lines = this.read().filter(function (l) {
        return l.item_code !== itemCode;
      });
      if (qty > 0) lines.push({ item_code: itemCode, qty: Math.min(MAX_QTY, qty) });
      this.write(lines);
      return lines;
    },

    remove: function (itemCode) { return this.setQty(itemCode, 0); },

    clear: function () { this.write([]); },

    count: function () {
      return this.read().reduce(function (n, l) { return n + l.qty; }, 0);
    },

    broadcast: function () {
      document.dispatchEvent(new CustomEvent('ropen:cart', { detail: { count: this.count() } }));
    }
  };

  /* ── nav ───────────────────────────────────────────────────────────── */
  function initNav() {
    var nav = $('.nav');
    var toggle = $('.nav-toggle');
    var links = $('.nav-links');

    if (nav) {
      var onScroll = function () { nav.classList.toggle('is-scrolled', window.scrollY > 8); };
      onScroll();
      window.addEventListener('scroll', onScroll, { passive: true });
    }

    if (toggle && links) {
      toggle.addEventListener('click', function () {
        var open = links.classList.toggle('is-open');
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
      // Close the mobile menu when a link is followed or Escape is pressed.
      links.addEventListener('click', function (e) {
        if (e.target.closest('a')) {
          links.classList.remove('is-open');
          toggle.setAttribute('aria-expanded', 'false');
        }
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && links.classList.contains('is-open')) {
          links.classList.remove('is-open');
          toggle.setAttribute('aria-expanded', 'false');
          toggle.focus();
        }
      });
    }
  }

  /* ── cart badge ────────────────────────────────────────────────────── */
  function initCartBadge() {
    var badge = $('.cart-count');
    var btn = $('.cart-btn');
    if (!badge) return;

    var paint = function (bump) {
      var n = Cart.count();
      badge.textContent = n > 99 ? '99+' : String(n);
      badge.classList.toggle('is-visible', n > 0);
      if (bump && n > 0 && btn) {
        btn.classList.remove('is-bumped');
        void btn.offsetWidth; // restart the animation
        btn.classList.add('is-bumped');
      }
    };

    paint(false);
    document.addEventListener('ropen:cart', function () { paint(true); });
    // Keep tabs in sync.
    window.addEventListener('storage', function (e) { if (e.key === CART_KEY) paint(false); });
  }

  /* ── add-to-cart buttons ───────────────────────────────────────────── */
  function initAddToCart() {
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-add-to-cart]');
      if (!btn) return;
      e.preventDefault();

      var code = btn.getAttribute('data-add-to-cart');
      var qtyInput = btn.getAttribute('data-qty-from') ? $(btn.getAttribute('data-qty-from')) : null;
      var qty = qtyInput ? Number(qtyInput.value) : 1;

      Cart.add(code, qty);
      toast((btn.getAttribute('data-name') || 'Item') + ' added to your basket', 'ok');

      if (btn.hasAttribute('data-then-cart')) {
        setTimeout(function () { location.href = '/cart'; }, 350);
      }
    });
  }

  /* ── quantity steppers ─────────────────────────────────────────────── */
  function initSteppers() {
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-step]');
      if (!btn) return;
      e.preventDefault();

      var wrap = btn.closest('.qty-stepper');
      var input = $('input', wrap);
      var next = Math.max(1, Math.min(MAX_QTY, (Number(input.value) || 1) + Number(btn.getAttribute('data-step'))));
      input.value = next;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
  }

  /* ── scroll reveal ─────────────────────────────────────────────────── */
  function initReveal() {
    var items = $$('.reveal');
    if (!items.length) return;

    if (!('IntersectionObserver' in window) ||
        window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      items.forEach(function (el) { el.classList.add('is-in'); });
      return;
    }

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-in');
        io.unobserve(entry.target);
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.05 });

    items.forEach(function (el) { io.observe(el); });
  }

  /* ── shop filtering ────────────────────────────────────────────────── */
  function initShop() {
    var root = $('[data-shop]');
    if (!root) return;

    var grid = $('[data-shop-results]', root);
    var chips = $$('[data-filter-group]', root);
    var searchInput = $('[data-shop-search]', root);
    var sortSelect = $('[data-shop-sort]', root);
    var countEl = $('[data-shop-count]', root);
    var timer = null;

    var state = {
      group: root.getAttribute('data-initial-group') || '',
      search: (searchInput && searchInput.value) || '',
      sort: (sortSelect && sortSelect.value) || 'featured'
    };

    function card(p) {
      var label = p.department === 'coffee' ? 'Coffee' : 'Wine';
      var price = p.in_stock
        ? '<div class="product-price">' + esc(p.price_formatted) + '</div>'
        : '<div class="product-price" style="font-size:.95rem;color:var(--ink-3)">Enquire</div>';
      var action = p.in_stock
        ? '<button class="btn btn-primary btn-sm" data-add-to-cart="' + esc(p.item_code) +
          '" data-name="' + esc(p.item_name) + '">Add</button>'
        : '<a class="btn btn-outline btn-sm" href="/contact">Enquire</a>';

      return '' +
        '<article class="product-card">' +
          '<a class="product-media" href="' + esc(p.route) + '" aria-label="' + esc(p.item_name) + '">' +
            '<img src="' + esc(p.image) + '" alt="' + esc(p.item_name) + '" loading="lazy" width="500" height="500">' +
            '<span class="product-tag' + (p.department === 'coffee' ? ' is-coffee' : '') + '">' + label + '</span>' +
          '</a>' +
          '<div class="product-body">' +
            '<h3 class="product-title"><a href="' + esc(p.route) + '">' + esc(p.item_name) + '</a></h3>' +
            '<p class="product-desc">' + esc(p.short_description || '') + '</p>' +
            '<div class="product-foot">' + price + action + '</div>' +
          '</div>' +
        '</article>';
    }

    function emptyState() {
      return '' +
        '<div class="empty-state" style="grid-column:1/-1">' +
          '<div class="icon-badge">' + svgIcon('search') + '</div>' +
          '<h3>Nothing matches that yet</h3>' +
          '<p>Try a different search, or clear the filters to see everything we have in stock.</p>' +
          '<p style="margin-top:1.25rem"><button class="btn btn-outline" data-shop-reset>Clear filters</button></p>' +
        '</div>';
    }

    function syncUrl() {
      var params = new URLSearchParams();
      if (state.group) params.set('group', state.group);
      if (state.search) params.set('q', state.search);
      if (state.sort && state.sort !== 'featured') params.set('sort', state.sort);
      var qs = params.toString();
      history.replaceState(null, '', qs ? '/shop?' + qs : '/shop');
    }

    function paintChips() {
      chips.forEach(function (chip) {
        var isOn = (chip.getAttribute('data-filter-group') || '') === state.group;
        chip.setAttribute('aria-pressed', isOn ? 'true' : 'false');
      });
    }

    function render() {
      grid.setAttribute('aria-busy', 'true');
      call('winery.ecommerce.api.search_products', {
        group: state.group, search: state.search, sort: state.sort
      })
        .then(function (data) {
          var products = (data && data.products) || [];
          grid.innerHTML = products.length ? products.map(card).join('') : emptyState();
          if (countEl) {
            countEl.textContent = products.length +
              (products.length === 1 ? ' product' : ' products');
          }
        })
        .catch(function (err) { toast(err.message, 'bad'); })
        .then(function () { grid.setAttribute('aria-busy', 'false'); });
    }

    chips.forEach(function (chip) {
      chip.addEventListener('click', function (e) {
        e.preventDefault();
        state.group = chip.getAttribute('data-filter-group') || '';
        paintChips();
        syncUrl();
        render();
      });
    });

    if (searchInput) {
      searchInput.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          state.search = searchInput.value.trim();
          syncUrl();
          render();
        }, 280);
      });
    }

    if (sortSelect) {
      sortSelect.addEventListener('change', function () {
        state.sort = sortSelect.value;
        syncUrl();
        render();
      });
    }

    root.addEventListener('click', function (e) {
      if (!e.target.closest('[data-shop-reset]')) return;
      state.group = '';
      state.search = '';
      if (searchInput) searchInput.value = '';
      paintChips();
      syncUrl();
      render();
    });

    paintChips();
  }

  /* ── cart page ─────────────────────────────────────────────────────── */
  function initCartPage() {
    var root = $('[data-cart-page]');
    if (!root) return;

    var body = $('[data-cart-body]', root);
    var summary = $('[data-cart-summary]', root);
    var notes = $('[data-cart-notes]', root);

    function line(l) {
      return '' +
        '<div class="cart-line" data-line="' + esc(l.item_code) + '">' +
          '<div class="cart-line-img"><img src="' + esc(l.image) + '" alt="' + esc(l.item_name) +
            '" loading="lazy" width="88" height="88"></div>' +
          '<div>' +
            '<h3 class="cart-line-name"><a href="' + esc(l.route) + '">' + esc(l.item_name) + '</a></h3>' +
            '<p class="cart-line-meta">' + esc(l.rate_formatted) + ' per ' + esc(l.uom) + '</p>' +
            '<div class="qty-stepper">' +
              '<button type="button" data-step="-1" aria-label="Decrease quantity">−</button>' +
              '<input type="number" min="1" max="' + MAX_QTY + '" value="' + l.qty +
                '" data-qty="' + esc(l.item_code) + '" aria-label="Quantity for ' + esc(l.item_name) + '">' +
              '<button type="button" data-step="1" aria-label="Increase quantity">+</button>' +
            '</div>' +
            '<div style="margin-top:.5rem"><button type="button" class="cart-line-remove" data-remove="' +
              esc(l.item_code) + '">Remove</button></div>' +
          '</div>' +
          '<div class="cart-line-amount">' + esc(l.amount_formatted) + '</div>' +
        '</div>';
    }

    function empty() {
      return '' +
        '<div class="empty-state">' +
          '<div class="icon-badge">' + svgIcon('cart') + '</div>' +
          '<h3>Your basket is empty</h3>' +
          '<p>Browse our banana wines and single-origin coffee, then add what you like.</p>' +
          '<p style="margin-top:1.5rem"><a class="btn btn-primary" href="/shop">Go to the shop</a></p>' +
        '</div>';
    }

    function render() {
      var lines = Cart.read();
      if (!lines.length) {
        body.innerHTML = empty();
        if (summary) summary.hidden = true;
        if (notes) notes.innerHTML = '';
        return;
      }

      call('winery.ecommerce.api.get_cart', { items: lines })
        .then(function (cart) {
          // The server may have dropped or capped lines; mirror that locally so
          // what the shopper sees is exactly what checkout will charge.
          var authoritative = cart.lines.map(function (l) {
            return { item_code: l.item_code, qty: l.qty };
          });
          if (JSON.stringify(authoritative) !== JSON.stringify(lines)) {
            localStorage.setItem(CART_KEY, JSON.stringify(authoritative));
            Cart.broadcast();
          }

          if (!cart.lines.length) {
            body.innerHTML = empty();
            if (summary) summary.hidden = true;
          } else {
            body.innerHTML = cart.lines.map(line).join('');
            if (summary) {
              summary.hidden = false;
              $('[data-summary-count]', summary).textContent = cart.count +
                (cart.count === 1 ? ' item' : ' items');
              $('[data-summary-total]', summary).textContent = cart.total_formatted;
            }
          }

          if (notes) {
            notes.innerHTML = (cart.notes || []).map(function (n) {
              return '<div class="notice notice-warn">' + esc(n) + '</div>';
            }).join('');
          }
        })
        .catch(function (err) {
          body.innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
        });
    }

    body.addEventListener('change', function (e) {
      var input = e.target.closest('[data-qty]');
      if (!input) return;
      Cart.setQty(input.getAttribute('data-qty'), input.value);
      render();
    });

    body.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-remove]');
      if (!btn) return;
      Cart.remove(btn.getAttribute('data-remove'));
      render();
      toast('Removed from basket');
    });

    render();
  }

  /* ── checkout ──────────────────────────────────────────────────────── */
  function initCheckout() {
    var root = $('[data-checkout]');
    if (!root) return;

    var form = $('[data-checkout-form]', root);
    var summary = $('[data-checkout-summary]', root);
    var payPanel = $('[data-pay-panel]', root);
    var submitBtn = $('[data-checkout-submit]', root);
    var errorBox = $('[data-checkout-error]', root);
    var poller = null;
    var deadline = 0;

    /* Render the priced basket into the order summary. */
    function renderSummary() {
      var lines = Cart.read();
      if (!lines.length) {
        location.href = '/cart';
        return;
      }
      call('winery.ecommerce.api.get_cart', { items: lines })
        .then(function (cart) {
          if (!cart.lines.length) { location.href = '/cart'; return; }
          $('[data-summary-lines]', summary).innerHTML = cart.lines.map(function (l) {
            return '<div class="summary-row"><span>' + esc(l.item_name) + ' × ' + l.qty +
                   '</span><span>' + esc(l.amount_formatted) + '</span></div>';
          }).join('');
          $('[data-summary-total]', summary).textContent = cart.total_formatted;
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Pay ' + cart.total_formatted + ' with M-Pesa';
          }
        })
        .catch(function (err) { showError(err.message); });
    }

    function showError(msg) {
      if (!errorBox) return toast(msg, 'bad');
      errorBox.innerHTML = '<div class="notice notice-error">' + esc(msg) + '</div>';
      errorBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function fieldValues() {
      var out = {};
      $$('[name]', form).forEach(function (el) { out[el.name] = el.value.trim(); });
      return out;
    }

    function validate(values) {
      var errors = {};
      if (!values.customer_name || values.customer_name.length < 2) {
        errors.customer_name = 'Please enter your full name.';
      }
      if (!/^(?:\+?254|0)?7\d{8}$/.test((values.phone || '').replace(/\s/g, ''))) {
        errors.phone = 'Enter a Safaricom number, e.g. 0712 345 678.';
      }
      if (values.email && !/^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$/.test(values.email)) {
        errors.email = 'That email address does not look right.';
      }
      if (!values.delivery_address || values.delivery_address.length < 5) {
        errors.delivery_address = 'Tell us where to deliver.';
      }

      $$('.error-text', form).forEach(function (el) { el.remove(); });
      $$('.field-error', form).forEach(function (el) { el.classList.remove('field-error'); });

      Object.keys(errors).forEach(function (name) {
        var input = $('[name="' + name + '"]', form);
        if (!input) return;
        input.classList.add('field-error');
        var msg = document.createElement('span');
        msg.className = 'error-text';
        msg.textContent = errors[name];
        input.parentNode.appendChild(msg);
      });

      return Object.keys(errors).length === 0;
    }

    /* Swap the form out for the "check your phone" panel. */
    function enterPaying(phone, token) {
      form.hidden = true;
      payPanel.hidden = false;
      $('[data-pay-phone]', payPanel).textContent = phone;
      deadline = Date.now() + 180000;
      poll(token);
    }

    function poll(token) {
      var tick = function () {
        if (Date.now() > deadline) {
          stopPolling();
          payPanel.innerHTML =
            '<div class="status-panel">' +
              '<div class="result-icon bad">!</div>' +
              '<h2>We did not get a confirmation</h2>' +
              '<p class="lede">Your M-Pesa prompt may have expired. If money left your account, ' +
              'contact us with the M-Pesa code and we will complete the order.</p>' +
              '<p style="margin-top:1.5rem"><a class="btn btn-primary" href="/order/' + esc(token) +
              '">See order status</a> <a class="btn btn-outline" href="/contact">Contact us</a></p>' +
            '</div>';
          return;
        }

        call('winery.ecommerce.api.payment_status', { order_token: token })
          .then(function (res) {
            if (res.status === 'Pending Payment') return;
            stopPolling();
            location.href = '/order/' + token;
          })
          .catch(function () { /* transient — the next tick retries */ });
      };
      poller = setInterval(tick, 3000);
      setTimeout(tick, 1200);
    }

    function stopPolling() { if (poller) { clearInterval(poller); poller = null; } }

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (errorBox) errorBox.innerHTML = '';

      var values = fieldValues();
      if (!validate(values)) return;

      var lines = Cart.read();
      if (!lines.length) { location.href = '/cart'; return; }

      submitBtn.disabled = true;
      var original = submitBtn.textContent;
      submitBtn.textContent = 'Sending M-Pesa request…';

      call('winery.ecommerce.api.start_checkout', { contact: values, items: lines })
        .then(function (res) {
          // The basket is now the server's problem — clear it so a back-button
          // press cannot double-order.
          Cart.clear();
          enterPaying(res.phone, res.order_token);
        })
        .catch(function (err) {
          submitBtn.disabled = false;
          submitBtn.textContent = original;
          showError(err.message);
        });
    });

    renderSummary();
  }

  /* ── order status page (auto-refresh while pending) ────────────────── */
  function initOrderPage() {
    var root = $('[data-order-page]');
    if (!root) return;
    if (root.getAttribute('data-order-status') !== 'Pending Payment') return;

    var token = root.getAttribute('data-order-token');
    var tries = 0;
    var poller = setInterval(function () {
      if (++tries > 40) return clearInterval(poller);
      call('winery.ecommerce.api.payment_status', { order_token: token })
        .then(function (res) {
          if (res.status !== 'Pending Payment') {
            clearInterval(poller);
            location.reload();
          }
        })
        .catch(function () { /* retry on the next tick */ });
    }, 4000);
  }

  /* ── contact form ──────────────────────────────────────────────────── */
  function initContactForm() {
    var form = $('[data-contact-form]');
    if (!form) return;

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = $('[type="submit"]', form);
      var status = $('[data-contact-status]', form);
      var values = {};
      $$('[name]', form).forEach(function (el) { values[el.name] = el.value.trim(); });

      btn.disabled = true;
      var original = btn.textContent;
      btn.textContent = 'Sending…';
      status.innerHTML = '';

      call('winery.ecommerce.api.submit_enquiry', values)
        .then(function () {
          form.reset();
          status.innerHTML = '<div class="notice notice-ok">Thank you — your message is with our ' +
            'team and we will reply within one working day.</div>';
        })
        .catch(function (err) {
          status.innerHTML = '<div class="notice notice-error">' + esc(err.message) + '</div>';
        })
        .then(function () {
          btn.disabled = false;
          btn.textContent = original;
        });
    });
  }

  /* ── boot ──────────────────────────────────────────────────────────── */
  function boot() {
    initNav();
    initCartBadge();
    initAddToCart();
    initSteppers();
    initReveal();
    initShop();
    initCartPage();
    initCheckout();
    initOrderPage();
    initContactForm();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  window.Ropen = { Cart: Cart, toast: toast, call: call };
})();
