/**
 * NavIMS - Inventory Management System
 * Dashboard Application JavaScript
 * Version 1.0.0
 */
(function () {
    "use strict";

    /* ===== CONSTANTS ===== */
    var STORAGE_KEY = "navims-theme-settings";

    var DEFAULTS = {
        theme: "light",
        layout: "vertical",
        sidebarSize: "default",
        sidebarColor: "dark",
        topbarColor: "light",
        layoutWidth: "fluid",
        layoutPosition: "fixed",
        direction: "ltr",
        preloader: false,
    };

    var DATA_ATTRS = {
        theme: "data-theme",
        layout: "data-layout",
        sidebarSize: "data-sidebar-size",
        sidebarColor: "data-sidebar",
        topbarColor: "data-topbar",
        layoutWidth: "data-layout-width",
        layoutPosition: "data-layout-position",
        direction: "dir",
    };

    /* ===== THEME MANAGER ===== */
    function ThemeManager() {
        this._listeners = [];
        this._settings = {};
        this._init();
    }

    ThemeManager.prototype._init = function () {
        this._loadFromStorage();
        this._applyAll();
    };

    ThemeManager.prototype._loadFromStorage = function () {
        try {
            var stored = localStorage.getItem(STORAGE_KEY);
            if (stored) {
                var parsed = JSON.parse(stored);
                this._settings = Object.assign({}, DEFAULTS, parsed);
            } else {
                this._settings = Object.assign({}, DEFAULTS);
            }
        } catch (e) {
            console.warn("NavIMS: Failed to load theme settings", e);
            this._settings = Object.assign({}, DEFAULTS);
        }
    };

    ThemeManager.prototype._saveToStorage = function () {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(this._settings));
        } catch (e) {
            console.warn("NavIMS: Failed to save theme settings", e);
        }
    };

    ThemeManager.prototype._applyAll = function () {
        var self = this;
        Object.keys(DATA_ATTRS).forEach(function (key) {
            self._applySetting(key, self._settings[key]);
        });
        this._applyPreloader();
    };

    ThemeManager.prototype._applySetting = function (key, value) {
        var attr = DATA_ATTRS[key];
        if (!attr) return;

        var el = document.documentElement;
        if (key === "direction") {
            el.setAttribute("dir", value);
        } else if (value && value !== "default" && value !== "fluid" && value !== "fixed") {
            el.setAttribute(attr, value);
        } else if (value === "default" || value === "fluid" || value === "fixed") {
            // For sidebarSize "default", remove the attribute to use CSS defaults
            if (key === "sidebarSize" && value === "default") {
                el.removeAttribute(attr);
            } else {
                el.setAttribute(attr, value);
            }
        } else {
            el.removeAttribute(attr);
        }

        this._settings[key] = value;
        this._saveToStorage();
        this._notifyListeners(key, value);
    };

    ThemeManager.prototype._applyPreloader = function () {
        var preloader = document.getElementById("preloader");
        if (!preloader) return;

        if (this._settings.preloader) {
            preloader.style.display = "flex";
            preloader.classList.remove("loaded");
        } else {
            preloader.classList.add("loaded");
            setTimeout(function () {
                preloader.style.display = "none";
            }, 400);
        }
    };

    ThemeManager.prototype._notifyListeners = function (key, value) {
        this._listeners.forEach(function (fn) {
            try {
                fn(key, value);
            } catch (e) {
                console.warn("NavIMS: Listener error", e);
            }
        });
    };

    ThemeManager.prototype.get = function (key) {
        return this._settings[key];
    };

    ThemeManager.prototype.getAll = function () {
        return Object.assign({}, this._settings);
    };

    ThemeManager.prototype.onChange = function (fn) {
        if (typeof fn === "function") {
            this._listeners.push(fn);
        }
    };

    ThemeManager.prototype.setTheme = function (value) {
        this._applySetting("theme", value);
    };

    ThemeManager.prototype.toggleTheme = function () {
        var current = this._settings.theme;
        this.setTheme(current === "dark" ? "light" : "dark");
    };

    ThemeManager.prototype.setLayout = function (value) {
        this._applySetting("layout", value);
    };

    ThemeManager.prototype.setSidebarSize = function (value) {
        this._applySetting("sidebarSize", value);
    };

    ThemeManager.prototype.setSidebarColor = function (value) {
        this._applySetting("sidebarColor", value);
    };

    ThemeManager.prototype.setTopbarColor = function (value) {
        this._applySetting("topbarColor", value);
    };

    ThemeManager.prototype.setLayoutWidth = function (value) {
        this._applySetting("layoutWidth", value);
    };

    ThemeManager.prototype.setLayoutPosition = function (value) {
        this._applySetting("layoutPosition", value);
    };

    ThemeManager.prototype.setDirection = function (value) {
        this._applySetting("direction", value);
    };

    ThemeManager.prototype.toggleDirection = function () {
        var current = this._settings.direction;
        this.setDirection(current === "rtl" ? "ltr" : "rtl");
    };

    ThemeManager.prototype.setPreloader = function (value) {
        this._settings.preloader = !!value;
        this._saveToStorage();
        this._applyPreloader();
    };

    ThemeManager.prototype.resetToDefaults = function () {
        this._settings = Object.assign({}, DEFAULTS);
        this._saveToStorage();
        this._applyAll();
        this._notifyListeners("reset", null);
    };

    /* ===== SIDEBAR ===== */
    function Sidebar(themeManager) {
        this._themeManager = themeManager;
        this._overlay = null;
        this._menuEl = null;
        this._isOpen = false;
        this._init();
    }

    Sidebar.prototype._init = function () {
        this._menuEl = document.querySelector(".app-menu");
        if (!this._menuEl) return;

        this._createOverlay();
        this._bindToggleButtons();
        this._bindSubmenus();
        this._bindMenuSections();
        this._bindHoverExpand();
        this._bindResize();
        this._handleMobileInit();
        this._highlightActiveItem();
        this._collapseInactiveSections();
    };

    Sidebar.prototype._createOverlay = function () {
        this._overlay = document.querySelector(".sidebar-overlay");
        if (!this._overlay) {
            this._overlay = document.createElement("div");
            this._overlay.className = "sidebar-overlay";
            document.body.appendChild(this._overlay);
        }

        var self = this;
        this._overlay.addEventListener("click", function () {
            self.close();
        });
    };

    Sidebar.prototype._bindToggleButtons = function () {
        var self = this;
        var toggleBtns = document.querySelectorAll("[data-toggle='sidebar'], .hamburger-icon");
        toggleBtns.forEach(function (btn) {
            btn.addEventListener("click", function (e) {
                e.preventDefault();
                if (self._isMobile()) {
                    self.toggle();
                } else {
                    // Toggle between default and small on desktop
                    var current = self._themeManager.get("sidebarSize");
                    if (current === "small") {
                        self._themeManager.setSidebarSize("default");
                    } else {
                        self._themeManager.setSidebarSize("small");
                    }
                }
            });
        });
    };

    Sidebar.prototype._bindSubmenus = function () {
        var self = this;
        var menuLinks = this._menuEl.querySelectorAll(".menu-link[data-toggle='submenu']");
        menuLinks.forEach(function (link) {
            link.addEventListener("click", function (e) {
                e.preventDefault();
                self._onSubmenuClick(this);
            });
        });
    };

    Sidebar.prototype._onSubmenuClick = function (link) {
        var menuItem = link.closest(".nav-item");
        if (!menuItem) return;

        var subMenu = menuItem.querySelector(".sub-menu");
        if (!subMenu) return;

        var isOpen = menuItem.classList.contains("open");

        // Close sibling menus
        var siblings = menuItem.parentElement.querySelectorAll(":scope > .nav-item.open");
        var self = this;
        siblings.forEach(function (sibling) {
            if (sibling !== menuItem) {
                self._collapseItem(sibling);
            }
        });

        if (isOpen) {
            this._collapseItem(menuItem);
        } else {
            this._expandItem(menuItem);
        }
    };

    Sidebar.prototype._expandItem = function (menuItem) {
        var subMenu = menuItem.querySelector(".sub-menu");
        if (!subMenu) return;

        menuItem.classList.add("open");

        // Smooth expand animation
        subMenu.style.maxHeight = "0px";
        subMenu.style.overflow = "hidden";

        var scrollHeight = subMenu.scrollHeight;
        requestAnimationFrame(function () {
            subMenu.style.maxHeight = scrollHeight + "px";
            subMenu.style.transition = "max-height 0.3s ease";

            var onEnd = function () {
                subMenu.style.maxHeight = "1000px";
                subMenu.style.overflow = "";
                subMenu.removeEventListener("transitionend", onEnd);
            };
            subMenu.addEventListener("transitionend", onEnd);
        });
    };

    Sidebar.prototype._collapseItem = function (menuItem) {
        var subMenu = menuItem.querySelector(".sub-menu");
        if (!subMenu) return;

        // Smooth collapse animation
        subMenu.style.maxHeight = subMenu.scrollHeight + "px";
        subMenu.style.overflow = "hidden";
        subMenu.style.transition = "max-height 0.3s ease";

        requestAnimationFrame(function () {
            subMenu.style.maxHeight = "0px";

            var onEnd = function () {
                menuItem.classList.remove("open");
                subMenu.removeEventListener("transitionend", onEnd);
            };
            subMenu.addEventListener("transitionend", onEnd);
        });
    };

    Sidebar.prototype._bindMenuSections = function () {
        // Collapsible menu sections by title
        var self = this;
        var titles = this._menuEl.querySelectorAll(".menu-title[data-toggle='section']");
        titles.forEach(function (title) {
            title.style.cursor = "pointer";
            title.addEventListener("click", function () {
                var items = self._getSectionItems(this);
                var isCollapsed = this.classList.contains("collapsed");
                if (isCollapsed) {
                    self._expandSection(this, items);
                } else {
                    self._collapseSection(this, items);
                }
            });
        });
    };

    Sidebar.prototype._getSectionItems = function (titleEl) {
        var items = [];
        var next = titleEl.nextElementSibling;
        while (next && !next.classList.contains("menu-title")) {
            items.push(next);
            next = next.nextElementSibling;
        }
        return items;
    };

    Sidebar.prototype._collapseSection = function (titleEl, items) {
        titleEl.classList.add("collapsed");
        items.forEach(function (item) {
            item.style.display = "none";
        });
    };

    Sidebar.prototype._expandSection = function (titleEl, items) {
        titleEl.classList.remove("collapsed");
        items.forEach(function (item) {
            item.style.display = "";
        });
    };

    Sidebar.prototype._collapseInactiveSections = function () {
        // Auto-collapse submenus that don't have active items
        if (!this._menuEl) return;
        var openItems = this._menuEl.querySelectorAll(".nav-item.open");
        var self = this;
        openItems.forEach(function (item) {
            if (!item.querySelector(".menu-link.active")) {
                self._collapseItem(item);
            }
        });
    };

    Sidebar.prototype._bindHoverExpand = function () {
        if (!this._menuEl) return;
        // Hover expand is handled purely by CSS for [data-sidebar-size="hover"]
    };

    Sidebar.prototype._bindResize = function () {
        var self = this;
        var resizeTimer;
        window.addEventListener("resize", function () {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(function () {
                if (!self._isMobile() && self._isOpen) {
                    self.close();
                }
            }, 250);
        });
    };

    Sidebar.prototype._handleMobileInit = function () {
        if (this._isMobile()) {
            // Ensure sidebar is closed on mobile init
            if (this._menuEl) {
                this._menuEl.classList.remove("open");
            }
            if (this._overlay) {
                this._overlay.classList.remove("open");
            }
        }
    };

    Sidebar.prototype._highlightActiveItem = function () {
        if (!this._menuEl) return;

        var currentPath = window.location.pathname;
        var links = this._menuEl.querySelectorAll(".menu-link");

        links.forEach(function (link) {
            var href = link.getAttribute("href");
            if (!href || href === "#") return;

            // Exact match or starts-with for nested routes
            if (href === currentPath || (currentPath.startsWith(href) && href !== "/")) {
                link.classList.add("active");
                var parent = link.closest(".nav-item");
                if (parent) {
                    parent.classList.add("active");
                }

                // Expand parent menus
                var parentMenu = link.closest(".sub-menu");
                while (parentMenu) {
                    var parentItem = parentMenu.closest(".nav-item");
                    if (parentItem) {
                        parentItem.classList.add("open", "active");
                        var sub = parentItem.querySelector(".sub-menu");
                        if (sub) {
                            sub.style.maxHeight = "1000px";
                        }
                    }
                    parentMenu = parentItem
                        ? parentItem.parentElement.closest(".sub-menu")
                        : null;
                }
            }
        });
    };

    Sidebar.prototype._isMobile = function () {
        return window.innerWidth < 992;
    };

    Sidebar.prototype.toggle = function () {
        if (this._isOpen) {
            this.close();
        } else {
            this.open();
        }
    };

    Sidebar.prototype.open = function () {
        if (!this._menuEl) return;
        this._menuEl.classList.add("open");
        if (this._overlay) {
            this._overlay.classList.add("open");
        }
        document.body.style.overflow = "hidden";
        this._isOpen = true;
    };

    Sidebar.prototype.close = function () {
        if (!this._menuEl) return;
        this._menuEl.classList.remove("open");
        if (this._overlay) {
            this._overlay.classList.remove("open");
        }
        document.body.style.overflow = "";
        this._isOpen = false;
    };

    /* ===== THEME CUSTOMIZER ===== */
    function ThemeCustomizer(themeManager) {
        this._themeManager = themeManager;
        this._el = null;
        this._overlay = null;
        this._isOpen = false;
        this._init();
    }

    ThemeCustomizer.prototype._init = function () {
        this._el = document.querySelector(".theme-customizer");
        this._overlay = document.querySelector(".theme-customizer-overlay");
        if (!this._el) return;

        this._bindToggle();
        this._bindClose();
        this._bindRadios();
        this._bindReset();
        this._syncRadiosToState();

        // Re-sync radios when theme settings change
        var self = this;
        this._themeManager.onChange(function () {
            self._syncRadiosToState();
        });
    };

    ThemeCustomizer.prototype._bindToggle = function () {
        var self = this;
        var toggleBtns = document.querySelectorAll("[data-toggle='theme-customizer']");
        toggleBtns.forEach(function (btn) {
            btn.addEventListener("click", function (e) {
                e.preventDefault();
                self.toggle();
            });
        });
    };

    ThemeCustomizer.prototype._bindClose = function () {
        var self = this;
        var closeBtns = this._el.querySelectorAll("[data-dismiss='theme-customizer']");
        closeBtns.forEach(function (btn) {
            btn.addEventListener("click", function (e) {
                e.preventDefault();
                self.close();
            });
        });

        if (this._overlay) {
            this._overlay.addEventListener("click", function () {
                self.close();
            });
        }
    };

    ThemeCustomizer.prototype._bindRadios = function () {
        var self = this;
        if (!this._el) return;

        var radios = this._el.querySelectorAll("input[type='radio'][name]");
        radios.forEach(function (radio) {
            radio.addEventListener("change", function () {
                var name = this.getAttribute("name");
                var value = this.value;

                var settingMap = {
                    "theme-mode": "setTheme",
                    "layout-mode": "setLayout",
                    "sidebar-size": "setSidebarSize",
                    "sidebar-color": "setSidebarColor",
                    "topbar-color": "setTopbarColor",
                    "layout-width": "setLayoutWidth",
                    "layout-position": "setLayoutPosition",
                    "layout-direction": "setDirection",
                };

                var method = settingMap[name];
                if (method && self._themeManager[method]) {
                    self._themeManager[method](value);
                }
            });
        });
    };

    ThemeCustomizer.prototype._bindReset = function () {
        var self = this;
        if (!this._el) return;

        var resetBtn = this._el.querySelector("[data-action='reset-settings']");
        if (resetBtn) {
            resetBtn.addEventListener("click", function (e) {
                e.preventDefault();
                self._themeManager.resetToDefaults();
                self._syncRadiosToState();
            });
        }
    };

    ThemeCustomizer.prototype._syncRadiosToState = function () {
        if (!this._el) return;

        var settings = this._themeManager.getAll();

        var radioMap = {
            "theme-mode": settings.theme,
            "layout-mode": settings.layout,
            "sidebar-size": settings.sidebarSize,
            "sidebar-color": settings.sidebarColor,
            "topbar-color": settings.topbarColor,
            "layout-width": settings.layoutWidth,
            "layout-position": settings.layoutPosition,
            "layout-direction": settings.direction,
        };

        Object.keys(radioMap).forEach(function (name) {
            var value = radioMap[name];
            var radio = document.querySelector(
                'input[name="' + name + '"][value="' + value + '"]'
            );
            if (radio) {
                radio.checked = true;
            }
        });
    };

    ThemeCustomizer.prototype.toggle = function () {
        if (this._isOpen) {
            this.close();
        } else {
            this.open();
        }
    };

    ThemeCustomizer.prototype.open = function () {
        if (!this._el) return;
        this._el.classList.add("open");
        if (this._overlay) {
            this._overlay.classList.add("open");
        }
        this._isOpen = true;
    };

    ThemeCustomizer.prototype.close = function () {
        if (!this._el) return;
        this._el.classList.remove("open");
        if (this._overlay) {
            this._overlay.classList.remove("open");
        }
        this._isOpen = false;
    };

    /* ===== UTILS ===== */
    var Utils = {
        getCookie: function (name) {
            var value = "; " + document.cookie;
            var parts = value.split("; " + name + "=");
            if (parts.length === 2) return parts.pop().split(";").shift();
            return null;
        },

        getCSRFToken: function () {
            // Django CSRF token: try meta tag, then cookie, then hidden input
            var meta = document.querySelector('meta[name="csrf-token"]');
            if (meta) return meta.getAttribute("content");

            var cookie = Utils.getCookie("csrftoken");
            if (cookie) return cookie;

            var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
            if (input) return input.value;

            return "";
        },

        _csrfSafeMethod: function (method) {
            return /^(GET|HEAD|OPTIONS|TRACE)$/i.test(method);
        },

        fetchJSON: function (url, options) {
            options = options || {};
            var method = (options.method || "GET").toUpperCase();

            var headers = Object.assign(
                {
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
                options.headers || {}
            );

            if (!Utils._csrfSafeMethod(method)) {
                headers["X-CSRFToken"] = Utils.getCSRFToken();
            }

            return fetch(url, Object.assign({}, options, { headers: headers }))
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error("HTTP " + response.status + ": " + response.statusText);
                    }
                    return response.json();
                });
        },

        setupAjaxCSRF: function () {
            // Setup for jQuery AJAX if jQuery is present
            if (typeof $ !== "undefined" && $.ajaxSetup) {
                $.ajaxSetup({
                    beforeSend: function (xhr, settings) {
                        if (!Utils._csrfSafeMethod(settings.type) && !this.crossDomain) {
                            xhr.setRequestHeader("X-CSRFToken", Utils.getCSRFToken());
                        }
                    },
                });
            }
        },

        hidePreloader: function () {
            var preloader = document.getElementById("preloader");
            if (preloader) {
                preloader.classList.add("loaded");
                setTimeout(function () {
                    preloader.style.display = "none";
                }, 400);
            }
        },

        initTooltipsAndPopovers: function () {
            // Bootstrap 5 tooltips
            if (typeof bootstrap !== "undefined") {
                var tooltipEls = document.querySelectorAll('[data-bs-toggle="tooltip"]');
                tooltipEls.forEach(function (el) {
                    new bootstrap.Tooltip(el);
                });

                var popoverEls = document.querySelectorAll('[data-bs-toggle="popover"]');
                popoverEls.forEach(function (el) {
                    new bootstrap.Popover(el);
                });
            }
        },

        toast: function (options) {
            /*
             * options: { title, message, type (success|danger|warning|info), duration }
             */
            options = options || {};
            var type = options.type || "info";
            var duration = options.duration || 4000;
            var title = options.title || "";
            var message = options.message || "";

            var container = document.querySelector(".toast-container");
            if (!container) {
                container = document.createElement("div");
                container.className =
                    "toast-container position-fixed top-0 end-0 p-3";
                container.style.zIndex = "1090";
                document.body.appendChild(container);
            }

            var colorMap = {
                success: "#22c55e",
                danger: "#ef4444",
                warning: "#f59e0b",
                info: "#3b82f6",
            };

            var toastEl = document.createElement("div");
            toastEl.className = "toast show";
            toastEl.setAttribute("role", "alert");
            toastEl.innerHTML =
                '<div class="toast-header">' +
                '<span class="rounded-circle d-inline-block me-2" style="width:12px;height:12px;background:' +
                (colorMap[type] || colorMap.info) +
                '"></span>' +
                "<strong class=\"me-auto\">" + (title || type.charAt(0).toUpperCase() + type.slice(1)) + "</strong>" +
                '<button type="button" class="btn-close btn-close-sm" aria-label="Close"></button>' +
                "</div>" +
                '<div class="toast-body">' + message + "</div>";

            container.appendChild(toastEl);

            // Close button
            var closeBtn = toastEl.querySelector(".btn-close");
            if (closeBtn) {
                closeBtn.addEventListener("click", function () {
                    toastEl.classList.remove("show");
                    setTimeout(function () {
                        toastEl.remove();
                    }, 300);
                });
            }

            // Auto-dismiss
            if (duration > 0) {
                setTimeout(function () {
                    toastEl.classList.remove("show");
                    setTimeout(function () {
                        toastEl.remove();
                    }, 300);
                }, duration);
            }

            return toastEl;
        },

        confirmDelete: function (options) {
            /*
             * options: { title, message, url, onConfirm, method }
             */
            options = options || {};
            var title = options.title || "Confirm Delete";
            var message = options.message || "Are you sure you want to delete this item? This action cannot be undone.";

            // Use Bootstrap modal if available
            if (typeof bootstrap !== "undefined") {
                var existingModal = document.getElementById("navims-confirm-modal");
                if (existingModal) existingModal.remove();

                var modalHTML =
                    '<div class="modal fade" id="navims-confirm-modal" tabindex="-1">' +
                    '<div class="modal-dialog modal-dialog-centered">' +
                    '<div class="modal-content">' +
                    '<div class="modal-header border-0">' +
                    '<h5 class="modal-title">' + title + "</h5>" +
                    '<button type="button" class="btn-close" data-bs-dismiss="modal"></button>' +
                    "</div>" +
                    '<div class="modal-body text-center py-4">' +
                    '<div class="mb-3"><i class="bi bi-exclamation-triangle text-danger" style="font-size:3rem"></i></div>' +
                    "<p>" + message + "</p>" +
                    "</div>" +
                    '<div class="modal-footer border-0 justify-content-center">' +
                    '<button type="button" class="btn btn-light" data-bs-dismiss="modal">Cancel</button>' +
                    '<button type="button" class="btn btn-danger" id="navims-confirm-btn">Delete</button>' +
                    "</div>" +
                    "</div></div></div>";

                document.body.insertAdjacentHTML("beforeend", modalHTML);

                var modalEl = document.getElementById("navims-confirm-modal");
                var modal = new bootstrap.Modal(modalEl);

                var confirmBtn = document.getElementById("navims-confirm-btn");
                confirmBtn.addEventListener("click", function () {
                    modal.hide();
                    if (typeof options.onConfirm === "function") {
                        options.onConfirm();
                    } else if (options.url) {
                        var method = (options.method || "POST").toUpperCase();
                        Utils.fetchJSON(options.url, { method: method })
                            .then(function () {
                                Utils.toast({ type: "success", message: "Item deleted successfully." });
                                if (options.reload !== false) {
                                    setTimeout(function () {
                                        window.location.reload();
                                    }, 800);
                                }
                            })
                            .catch(function (err) {
                                Utils.toast({ type: "danger", message: "Delete failed: " + err.message });
                            });
                    }
                });

                modalEl.addEventListener("hidden.bs.modal", function () {
                    modalEl.remove();
                });

                modal.show();
            } else {
                // Fallback to native confirm
                if (confirm(message)) {
                    if (typeof options.onConfirm === "function") {
                        options.onConfirm();
                    }
                }
            }
        },

        tableFilter: function (inputSelector, tableSelector) {
            var input = document.querySelector(inputSelector);
            var table = document.querySelector(tableSelector);
            if (!input || !table) return;

            input.addEventListener("input", function () {
                var filter = this.value.toLowerCase().trim();
                var rows = table.querySelectorAll("tbody tr");

                rows.forEach(function (row) {
                    var text = row.textContent.toLowerCase();
                    row.style.display = text.indexOf(filter) > -1 ? "" : "none";
                });
            });
        },
    };

    /* ===== PRIVATE FUNCTIONS ===== */
    function _bindDeleteConfirmations() {
        document.addEventListener("click", function (e) {
            var btn = e.target.closest("[data-confirm-delete]");
            if (!btn) return;

            e.preventDefault();
            var url = btn.getAttribute("data-confirm-delete") || btn.getAttribute("href");
            var title = btn.getAttribute("data-confirm-title") || "Confirm Delete";
            var message = btn.getAttribute("data-confirm-message") || undefined;
            var method = btn.getAttribute("data-method") || "POST";

            Utils.confirmDelete({
                title: title,
                message: message,
                url: url,
                method: method,
            });
        });
    }

    function _bindDarkModeToggle() {
        var toggleBtns = document.querySelectorAll("[data-toggle='dark-mode']");
        toggleBtns.forEach(function (btn) {
            btn.addEventListener("click", function (e) {
                e.preventDefault();
                if (window.NavIMS && window.NavIMS.themeManager) {
                    window.NavIMS.themeManager.toggleTheme();

                    // Update icon if present
                    var icon = this.querySelector("i");
                    if (icon) {
                        var isDark = window.NavIMS.themeManager.get("theme") === "dark";
                        icon.className = isDark ? "bi bi-sun" : "bi bi-moon";
                    }
                }
            });
        });
    }

    function _bindFullscreenToggle() {
        var toggleBtns = document.querySelectorAll("[data-toggle='fullscreen']");
        toggleBtns.forEach(function (btn) {
            btn.addEventListener("click", function (e) {
                e.preventDefault();
                if (!document.fullscreenElement) {
                    document.documentElement.requestFullscreen().catch(function () {});
                } else {
                    document.exitFullscreen().catch(function () {});
                }
            });
        });
    }

    function _bindSearchBox() {
        var searchInputs = document.querySelectorAll(".app-search .form-control");
        searchInputs.forEach(function (input) {
            var dropdown = input.closest(".app-search").querySelector(".dropdown-menu");
            if (!dropdown) return;

            input.addEventListener("focus", function () {
                if (this.value.trim().length > 0) {
                    dropdown.classList.add("show");
                }
            });

            input.addEventListener("input", function () {
                if (this.value.trim().length > 0) {
                    dropdown.classList.add("show");
                } else {
                    dropdown.classList.remove("show");
                }
            });

            input.addEventListener("blur", function () {
                // Delay to allow click on dropdown items
                setTimeout(function () {
                    dropdown.classList.remove("show");
                }, 200);
            });
        });
    }

    function _bindBackToTop() {
        var btn = document.querySelector(".btn-back-to-top");
        if (!btn) return;

        window.addEventListener("scroll", function () {
            if (window.scrollY > 300) {
                btn.classList.add("show");
            } else {
                btn.classList.remove("show");
            }
        });

        btn.addEventListener("click", function () {
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    }

    /* ===== INIT ===== */
    function init() {
        var themeManager = new ThemeManager();
        var sidebar = new Sidebar(themeManager);
        var customizer = new ThemeCustomizer(themeManager);

        // Bind features
        _bindDeleteConfirmations();
        _bindDarkModeToggle();
        _bindFullscreenToggle();
        _bindSearchBox();
        _bindBackToTop();

        // Setup CSRF for AJAX
        Utils.setupAjaxCSRF();

        // Init Bootstrap components
        Utils.initTooltipsAndPopovers();

        // Hide preloader after page loads
        Utils.hidePreloader();

        // Expose public API
        window.NavIMS = {
            themeManager: themeManager,
            sidebar: sidebar,
            customizer: customizer,
            utils: Utils,
            version: "1.0.0",
        };
    }

    /* ===== BOOTSTRAP ON DOM READY ===== */
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
