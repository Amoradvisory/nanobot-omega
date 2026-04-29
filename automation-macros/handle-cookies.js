/**
 * handle-cookies.js — Injecteur Universel RGPD/Cookies
 *
 * Detecte et clique automatiquement sur les bannieres cookies/RGPD.
 * Fonctionne sur Google, YouTube, LinkedIn, Facebook, et la plupart
 * des sites utilisant les frameworks cookies courants (OneTrust, Didomi,
 * Cookiebot, Quantcast, TrustArc, Axeptio, etc.)
 *
 * USAGE (via Playwright MCP browser_evaluate) :
 *   browser_evaluate file:"C:\AI\nanobot-omega\automation-macros\handle-cookies.js"
 *
 * USAGE (via exec dans Gemini) :
 *   exec("node C:\\AI\\nanobot-omega\\automation-macros\\handle-cookies.js")
 *
 * Retourne : { handled: true/false, method: "...", domain: "..." }
 */

(function handleCookies() {
    "use strict";

    const result = { handled: false, method: "none", domain: location.hostname, attempts: [] };

    // ================================================================
    // STRATEGIES PAR PRIORITE
    // Chaque strategie retourne true si elle a clique avec succes
    // ================================================================

    const strategies = [

        // --- 1. GOOGLE / YOUTUBE (consent.google.com) ---
        {
            name: "google-consent",
            match: () => /google\.|youtube\./.test(location.hostname) ||
                         document.querySelector('[action*="consent.google"]'),
            run: () => {
                // Bouton "Tout accepter" dans les differentes langues
                const selectors = [
                    'button[aria-label*="Accept all"]',
                    'button[aria-label*="Tout accepter"]',
                    'button[aria-label*="Alle akzeptieren"]',
                    '[id="L2AGLb"]',                          // Google search consent
                    '[id="yDmH0d"] button:last-child',        // YouTube consent
                    'form[action*="consent"] button:nth-child(2)',
                    'button.VfPpkd-LgbsSe[data-ved]',        // Material Design button
                    'tp-yt-paper-dialog button[aria-label*="Accept"]',
                    'tp-yt-paper-dialog button[aria-label*="Accepter"]',
                    '.consent-bump button:last-of-type',
                ];
                for (const sel of selectors) {
                    const btn = document.querySelector(sel);
                    if (btn && btn.offsetParent !== null) {
                        btn.click();
                        return true;
                    }
                }
                // Fallback : chercher par texte "Tout accepter" / "Accept all"
                const buttons = document.querySelectorAll('button, [role="button"]');
                for (const btn of buttons) {
                    const text = (btn.textContent || "").trim().toLowerCase();
                    if (/^(tout accepter|accept all|alle akzeptieren|acepto todo)$/.test(text)) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }
        },

        // --- 2. LINKEDIN ---
        {
            name: "linkedin",
            match: () => /linkedin\.com/.test(location.hostname),
            run: () => {
                const selectors = [
                    'button[action-type="ACCEPT"]',
                    '.artdeco-global-alert__action button:first-child',
                    'button.cookie-consent__accept-btn',
                    '[data-test-id="cookie-banner-accept"]',
                ];
                for (const sel of selectors) {
                    const btn = document.querySelector(sel);
                    if (btn) { btn.click(); return true; }
                }
                return false;
            }
        },

        // --- 3. ONETRUST (tres repandu : BBC, Reuters, etc.) ---
        {
            name: "onetrust",
            match: () => !!document.querySelector('#onetrust-banner-sdk, .onetrust-pc-dark-filter'),
            run: () => {
                const btn = document.querySelector('#onetrust-accept-btn-handler') ||
                            document.querySelector('.onetrust-close-btn-handler');
                if (btn) { btn.click(); return true; }
                return false;
            }
        },

        // --- 4. DIDOMI ---
        {
            name: "didomi",
            match: () => !!document.querySelector('#didomi-host, [id*="didomi"]'),
            run: () => {
                const btn = document.querySelector('#didomi-notice-agree-button') ||
                            document.querySelector('[id*="didomi"] button[class*="agree"]');
                if (btn) { btn.click(); return true; }
                return false;
            }
        },

        // --- 5. COOKIEBOT ---
        {
            name: "cookiebot",
            match: () => !!document.querySelector('#CybotCookiebotDialog, [id*="Cookiebot"]'),
            run: () => {
                const btn = document.querySelector('#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll') ||
                            document.querySelector('#CybotCookiebotDialogBodyButtonAccept') ||
                            document.querySelector('[id*="CookiebotDialog"] .CybotCookiebotDialogBodyButton');
                if (btn) { btn.click(); return true; }
                return false;
            }
        },

        // --- 6. QUANTCAST (GDPR Choice) ---
        {
            name: "quantcast",
            match: () => !!document.querySelector('.qc-cmp2-container, [class*="qc-cmp"]'),
            run: () => {
                const btn = document.querySelector('.qc-cmp2-summary-buttons button:nth-child(2)') ||
                            document.querySelector('button[mode="primary"][class*="qc"]');
                if (btn) { btn.click(); return true; }
                return false;
            }
        },

        // --- 7. AXEPTIO ---
        {
            name: "axeptio",
            match: () => !!document.querySelector('#axeptio_overlay, [id*="axeptio"]'),
            run: () => {
                const btn = document.querySelector('[id*="axeptio"] button[class*="accept"]') ||
                            document.querySelector('#axeptio_btn_acceptAll');
                if (btn) { btn.click(); return true; }
                return false;
            }
        },

        // --- 8. TRUSTARC ---
        {
            name: "trustarc",
            match: () => !!document.querySelector('#truste-consent-track, .truste-banner'),
            run: () => {
                const btn = document.querySelector('#truste-consent-button') ||
                            document.querySelector('.truste-banner button');
                if (btn) { btn.click(); return true; }
                return false;
            }
        },

        // --- 9. GENERIQUE — Pattern universel ---
        {
            name: "generic",
            match: () => true,  // Toujours tenter en dernier recours
            run: () => {
                // Mots-cles acceptation dans toutes les langues courantes
                const acceptPatterns = [
                    /^(accept|accepter|tout accepter|accept all|agree|agree all|ok|i agree)$/i,
                    /^(j'accepte|accepter tout|autoriser|allow all|consent|continuer)$/i,
                    /^(alle akzeptieren|akzeptieren|aceptar|aceptar todo|acepto)$/i,
                    /^(accetta|accetta tutto|aceitar|aceitar tudo)$/i,
                ];

                // Selecteurs de bannieres cookies generiques
                const bannerSelectors = [
                    '[class*="cookie"] button',
                    '[class*="consent"] button',
                    '[class*="gdpr"] button',
                    '[class*="privacy"] button',
                    '[id*="cookie"] button',
                    '[id*="consent"] button',
                    '[role="dialog"] button',
                    '[class*="banner"] button',
                    '[class*="modal"] button',
                    '[class*="overlay"] button',
                ];

                // Chercher un bouton d'acceptation dans les bannieres
                for (const sel of bannerSelectors) {
                    const buttons = document.querySelectorAll(sel);
                    for (const btn of buttons) {
                        const text = (btn.textContent || "").trim();
                        if (acceptPatterns.some(p => p.test(text))) {
                            btn.click();
                            return true;
                        }
                    }
                }

                // Derniere chance : tout bouton visible avec texte "accept"
                const allBtns = document.querySelectorAll('button, a[role="button"], [role="button"]');
                for (const btn of allBtns) {
                    if (btn.offsetParent === null) continue;  // invisible
                    const text = (btn.textContent || "").trim();
                    if (acceptPatterns.some(p => p.test(text))) {
                        btn.click();
                        return true;
                    }
                }

                return false;
            }
        }
    ];

    // ================================================================
    // EXECUTION
    // ================================================================
    for (const strategy of strategies) {
        try {
            if (strategy.match()) {
                result.attempts.push(strategy.name);
                if (strategy.run()) {
                    result.handled = true;
                    result.method = strategy.name;
                    break;
                }
            }
        } catch (e) {
            result.attempts.push(`${strategy.name}:ERROR:${e.message}`);
        }
    }

    return result;
})();
