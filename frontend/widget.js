(function () {
  "use strict";

  var cfg = window.EnlevaChatConfig || {};
  var apiBase = (cfg.apiUrl || "/chat").replace(/\/chat\/?$/, "");
  var chatUrl = cfg.apiUrl || "/chat";
  var position = cfg.position === "left" ? "left" : "right";
    var apiToken = cfg.apiToken || "";
    // Mitigação anti-scanner (visível no browser — NÃO é autenticação de sessão).
    // Preferir EnlevaChatConfig.apiToken; senão o valor vindo de /config/public.
  var storageKey = "enleva-chat-history-v1";
  var sessionKey = "enleva-chat-session-v1";
  var GENERIC_ERROR =
    "Não foi possível contactar o serviço. Tente novamente ou abra um chamado no GLPI (TI) ou em Atendimento ao Colaborador (RH).";
  var DEFAULT_ICON = "💬";
  var REFUSAL_LABELS = {
    out_of_scope: "Fora do escopo",
    no_context: "Sem resposta na base",
    sensitive: "Conteúdo bloqueado"
  };

  function refusalLabel(reason) {
    if (reason && REFUSAL_LABELS[reason]) return REFUSAL_LABELS[reason];
    return "Sem resposta na base";
  }

  function uid() {
    return "s-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  }

  function getSessionId() {
    var id = sessionStorage.getItem(sessionKey);
    if (!id) {
      id = uid();
      sessionStorage.setItem(sessionKey, id);
    }
    return id;
  }

  function setSessionId(id) {
    if (!id) return;
    sessionStorage.setItem(sessionKey, id);
  }

  function loadHistory() {
    try {
      return JSON.parse(sessionStorage.getItem(storageKey) || "[]");
    } catch (e) {
      return [];
    }
  }

  function saveHistory(items) {
    sessionStorage.setItem(storageKey, JSON.stringify(items));
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function extractErrorDetail(payload) {
    if (!payload) return null;
    if (typeof payload.detail === "string") return payload.detail;
    if (Array.isArray(payload.detail) && payload.detail[0]) {
      var first = payload.detail[0];
      if (typeof first === "string") return first;
      if (first && first.msg) return first.msg;
    }
    if (typeof payload.message === "string") return payload.message;
    return null;
  }

  function ensureCss() {
    if (document.getElementById("enleva-chat-css")) return;
    var link = document.createElement("link");
    link.id = "enleva-chat-css";
    link.rel = "stylesheet";
    var script = document.currentScript;
    var src =
      script && script.src
        ? script.src.replace(/widget\.js.*$/, "widget.css")
        : "/static/widget.css";
    link.href = cfg.cssUrl || src;
    document.head.appendChild(link);
  }

  function applyTheme(rootEl) {
    // Defaults medidos na intranet.enlevasaude.com (DevTools, ago/2026)
    // CTAs Parabenizar/Enviar: ~#1e4076; token --lp-secondary-color: #1c51a0
    // Marca/nav/badge/FAB: --lp-primary-color #f05b78
    var primary = cfg.primaryColor || cfg.primary || "#1c51a0";
    var accent = cfg.accentColor || cfg.accent || "#F05B78";
    var bg = cfg.bgColor || cfg.backgroundColor || "#EEF6F7";
    var text = cfg.textColor || "#707276";
    var muted = cfg.mutedColor || "#7A7E83";
    var border = cfg.borderColor || "#D9E0E3";
    // Bolha do usuário = primary/CTA (#1c51a0), salvo override explícito
    var userBg = cfg.userBubbleColor || primary;

    rootEl.style.setProperty("--enleva-chat-primary-color", primary);
    rootEl.style.setProperty("--enleva-chat-accent-color", accent);
    rootEl.style.setProperty("--enleva-chat-bg", bg);
    rootEl.style.setProperty("--enleva-chat-text-color", text);
    rootEl.style.setProperty("--enleva-chat-muted-color", muted);
    rootEl.style.setProperty("--enleva-chat-border-color", border);
    rootEl.style.setProperty("--enleva-chat-user-bg", userBg);
    rootEl.style.setProperty("--enleva-chat-on-primary", "#FCFCFC");
    rootEl.style.setProperty("--enleva-chat-surface", "#FFFFFF");

    // Aliases internos do widget (só no root do widget)
    rootEl.style.setProperty("--enleva-bg", primary);
    rootEl.style.setProperty("--enleva-accent", accent);
    rootEl.style.setProperty("--enleva-surface", bg);
    rootEl.style.setProperty("--enleva-text", text);
    rootEl.style.setProperty("--enleva-muted", muted);
    rootEl.style.setProperty("--enleva-border", border);
    rootEl.style.setProperty("--enleva-user", userBg);
  }

  function fillLauncherIcon(launcher) {
    var icon = cfg.icon != null && cfg.icon !== "" ? cfg.icon : DEFAULT_ICON;
    launcher.innerHTML = "";
    // URL de imagem
    if (typeof icon === "string" && /^(https?:|\/|\.\/|data:image)/i.test(icon)) {
      var img = document.createElement("img");
      img.src = icon;
      img.alt = "Chat";
      img.className = "enleva-launcher-img";
      launcher.appendChild(img);
      return;
    }
    // Emoji ou texto curto
    launcher.textContent = String(icon);
  }

  function mount() {
    ensureCss();
    var root = el("div", "enleva-chat-root");
    root.id = "enleva-chat-root";
    if (position === "left") root.classList.add("enleva-left");
    applyTheme(root);

    var panel = el("div", "enleva-panel");
    var header = el("div", "enleva-header");
    var title = el("h2", null, "Assistente");
    var closeBtn = el("button", null, "×");
    closeBtn.setAttribute("aria-label", "Fechar chat");
    header.appendChild(title);
    header.appendChild(closeBtn);

    var messages = el("div", "enleva-messages");
    var form = el("form", "enleva-form");
    var input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Pergunte sobre procedimentos internos...";
    input.autocomplete = "off";
    var send = el("button", null, "Enviar");
    send.type = "submit";
    form.appendChild(input);
    form.appendChild(send);

    panel.appendChild(header);
    panel.appendChild(messages);
    panel.appendChild(form);

    var launcher = el("button", "enleva-launcher");
    launcher.type = "button";
    launcher.setAttribute("aria-label", "Abrir chat");
    fillLauncherIcon(launcher);

    root.appendChild(panel);
    root.appendChild(launcher);
    document.body.appendChild(root);

    var history = loadHistory();
    var botName = "Assistente";

    function render() {
      messages.innerHTML = "";
      history.forEach(function (item) {
        var classes = "enleva-msg " + item.role;
        if (item.role === "bot" && item.refused) classes += " refused";
        var bubble = el("div", classes);

        if (item.role === "bot" && item.refused) {
          var label = el(
            "div",
            "enleva-refused-label",
            refusalLabel(item.refusalReason)
          );
          bubble.appendChild(label);
        }

        var body = el("div", "enleva-msg-text", item.text);
        bubble.appendChild(body);

        if (item.sources && item.sources.length) {
          var src = el(
            "div",
            "enleva-sources",
            "Fontes: " +
              item.sources
                .map(function (s) {
                  return s.title || s.source;
                })
                .join(", ")
          );
          bubble.appendChild(src);
        }
        messages.appendChild(bubble);
      });
      messages.scrollTop = messages.scrollHeight;
    }

    function setOpen(open) {
      panel.classList.toggle("open", open);
    }

    function pushBotMessage(text, opts) {
      opts = opts || {};
      history.push({
        role: "bot",
        text: text,
        sources: opts.sources || [],
        refused: !!opts.refused,
        refusalReason: opts.refusalReason || null
      });
      saveHistory(history);
      render();
    }

    launcher.addEventListener("click", function () {
      setOpen(true);
    });
    closeBtn.addEventListener("click", function () {
      setOpen(false);
    });

    fetch((apiBase || "") + "/config/public")
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (data && data.bot_name) {
          botName = data.bot_name;
          title.textContent = botName;
          if (!history.length) {
            pushBotMessage(
              "Olá! Sou " +
                botName +
                ". Posso ajudar com dúvidas cobertas pela base interna da Rede Enleva."
            );
          }
        }
        // Token provisório servido pelo backend (mesmo valor do .env) — visível no JS
        if (!cfg.apiToken && data && data.widget_api_token) {
          apiToken = data.widget_api_token;
        }
      })
      .catch(function () {
        title.textContent = botName;
        if (!history.length) {
          pushBotMessage(
            "Olá! Posso ajudar com dúvidas cobertas pela base interna da Rede Enleva."
          );
        }
      });

    if (history.length) render();

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var text = (input.value || "").trim();
      if (!text) return;
      input.value = "";
      history.push({ role: "user", text: text });
      saveHistory(history);
      render();
      send.disabled = true;

      var headers = { "Content-Type": "application/json" };
      if (apiToken) headers["X-Widget-Token"] = apiToken;

      fetch(chatUrl, {
        method: "POST",
        headers: headers,
        body: JSON.stringify({ message: text, session_id: getSessionId() })
      })
        .then(function (r) {
          return r
            .json()
            .catch(function () {
              return {};
            })
            .then(function (data) {
              return { ok: r.ok, status: r.status, data: data };
            });
        })
        .then(function (res) {
          if (res.status === 401) {
            pushBotMessage(
              "Não foi possível autorizar o assistente neste navegador. Recarregue a página ou abra a intranet pelo endereço oficial.",
              { refused: true }
            );
            return;
          }
          if (res.status === 429) {
            var detail =
              extractErrorDetail(res.data) ||
              "Muitas mensagens em pouco tempo. Tente novamente em instantes.";
            pushBotMessage(detail, { refused: true });
            return;
          }
          if (!res.ok) {
            pushBotMessage(GENERIC_ERROR);
            return;
          }
          var data = res.data || {};
          if (data.bot_name) {
            botName = data.bot_name;
            title.textContent = botName;
          }
          // Sync session_id do servidor quando diferente
          if (data.session_id && data.session_id !== getSessionId()) {
            setSessionId(data.session_id);
          }
          pushBotMessage(data.reply || "Sem resposta.", {
            sources: data.sources || [],
            refused: !!data.refused,
            refusalReason: data.refusal_reason || null
          });
        })
        .catch(function () {
          pushBotMessage(GENERIC_ERROR);
        })
        .finally(function () {
          send.disabled = false;
          input.focus();
        });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
