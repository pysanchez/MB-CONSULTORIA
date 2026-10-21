const isLocalFrontend = ["localhost", "127.0.0.1"].includes(window.location.hostname)
  && window.location.port !== "8000";
const API_URL = isLocalFrontend
  ? `${window.location.protocol}//${window.location.hostname}:8000`
  : "";
const PAGE_SIZE = 50;
const pendingCreditNumber = new URLSearchParams(window.location.search)
  .get("credito")
  ?.trim() || "";

if (pendingCreditNumber) {
  const cleanUrl = new URL(window.location.href);
  cleanUrl.searchParams.delete("credito");
  window.history.replaceState({}, "", cleanUrl);
}
const RESULT_LABELS = {
  promesa: "Promesa de pago",
  negativa: "Negativa de pago",
  recado: "Se dejó recado",
  pago_reportado: "Pago reportado",
  sin_acuerdo: "Contacto sin acuerdo",
  no_contesto: "No contestó",
  numero_incorrecto: "Número incorrecto",
};

const uploadForm = document.getElementById("upload-form");
const financialSelect = document.getElementById("financial-select");
const fileInput = document.getElementById("archivo-cartera");
const fileName = document.getElementById("file-name");
const importButton = document.getElementById("import-button");
const importStatus = document.getElementById("import-status");

const portfolioButton = document.getElementById("refresh-portfolio");
const portfolioList = document.getElementById("portfolio-list");
const portfolioStatus = document.getElementById("portfolio-status");
const portfolioResults = document.getElementById("portfolio-results");
const portfolioLoadMoreButton = document.getElementById("portfolio-load-more");
const loginForm = document.getElementById("login-form");
const loginPassword = document.getElementById("login-password");
const loginStatus = document.getElementById("login-status");
const loginScreen = document.getElementById("login-screen");
const workspace = document.getElementById("inicio");
const breadcrumbView = document.getElementById("breadcrumb-view");
const views = {
  home: document.getElementById("view-home"),
  portfolio: document.getElementById("view-portfolio"),
  management: document.getElementById("view-gestion"),
  upload: document.getElementById("view-upload"),
  reports: document.getElementById("view-reports"),
};
const viewLabels = {
  home: "Inicio",
  portfolio: "Mi cartera",
  management: "Registrar gestión",
  upload: "Cargar cartera",
  reports: "Reportes",
};
const managementSearchForm = document.getElementById("management-account-search");
const managementSearchInput = document.getElementById("management-search-input");
const managementSearchStatus = document.getElementById("management-search-status");
const managementAccountResults = document.getElementById("management-account-results");
const selectedAccountPanel = document.getElementById("selected-account-panel");
const accountDetails = document.getElementById("account-details");
const managementForm = document.getElementById("management-form");
const callResultSelect = document.getElementById("call-result");
const promiseFields = document.getElementById("promise-fields");
const managementHistoryList = document.getElementById("management-history-list");
const latestManagementSummary = document.getElementById("latest-management-summary");
const personContactedSelect = document.getElementById("person-contacted");
const referenceForm = document.getElementById("reference-form");

let portfolioOffset = 0;
let portfolioLoaded = false;
let selectedAccount = null;
let sessionStartedAt = null;

async function getJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: "include",
    ...options,
  });
  const result = await response.json();

  if (!response.ok) {
    throw new Error(result.detail || "La solicitud no se pudo completar.");
  }

  return result;
}

async function loadFinancialOptions() {
  if (workspace.hidden) {
    return;
  }

  const financials = await getJson(`${API_URL}/api/financieras`);
  financialSelect.replaceChildren(
    new Option("Selecciona una financiera", ""),
  );

  for (const financial of financials) {
    financialSelect.add(
      new Option(financial.nombre_financiera, financial.id_financiera),
    );
  }
}

function appendCell(row, value) {
  const cell = document.createElement("td");
  cell.textContent = value || "—";
  row.append(cell);
}

function appendAccountRows(target, accounts) {
  for (const account of accounts) {
    const row = document.createElement("tr");
    appendCell(row, account.cliente);
    appendCell(row, account.numero_credito);
    appendCell(row, account.celular || account.casa);
    appendCell(row, account.financiera?.nombre_financiera);
    appendCell(row, account.estatus);

    const actionCell = document.createElement("td");
    const actionButton = document.createElement("button");
    actionButton.className = "button button-primary table-action";
    actionButton.type = "button";
    actionButton.textContent = "Registrar llamada";
    actionButton.addEventListener("click", () => selectAccount(account));
    actionCell.append(actionButton);
    row.append(actionCell);
    target.append(row);
  }
}

function displayValue(value, fallback = "Sin dato") {
  if (value === null || value === undefined || String(value).trim() === "") {
    return fallback;
  }

  return String(value);
}

function displayDate(value) {
  if (!value) {
    return "Sin dato";
  }

  const date = new Date(`${String(value).slice(0, 10)}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? String(value)
    : new Intl.DateTimeFormat("es-MX", {
        day: "numeric",
        month: "long",
        year: "numeric",
      }).format(date);
}

function displayMoney(value) {
  if (value === null || value === undefined || String(value).trim() === "") {
    return "Sin dato";
  }

  const amount = Number(value);
  return Number.isFinite(amount)
    ? new Intl.NumberFormat("es-MX", {
        style: "currency",
        currency: "MXN",
        minimumFractionDigits: 2,
      }).format(amount)
    : String(value);
}

function daysSince(value) {
  if (!value) {
    return "Sin fecha de último pago";
  }

  const date = new Date(`${String(value).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return "No se pudo calcular";
  }

  const days = Math.max(0, Math.floor((Date.now() - date.getTime()) / 86400000));
  return `${days} ${days === 1 ? "día" : "días"}`;
}

function renderAccountDetails(account) {
  const address = account.domicilio_completo
    || [
      account.calle_numero,
      account.colonia,
      account.ciudad,
      account.estado,
      account.codigo_postal,
    ].filter(Boolean).join(", ");
  const groups = [
    {
      title: "Datos fundamentales",
      items: [
        ["Nombre completo", account.cliente],
        ["Número de teléfono", account.celular || account.casa],
        ["Domicilio", address],
        ["Adeudo inicial", displayMoney(account.sdo_vencido_inicial)],
        ["Adeudo al día", displayMoney(account.saldo_vencido_actual)],
        ["Capital original", displayMoney(account.capital)],
        ["Capital vigente", displayMoney(account.sdo_capital)],
        ["Adeudo total", displayMoney(account.total || account.sdo_actual)],
      ],
    },
    {
      title: "Referencias",
      items: [
        ["Referencia 1 · Nombre", account.ref1_nombre],
        ["Referencia 1 · Número de teléfono", account.ref1_tel || account.referencia_1],
        ["Referencia 2 · Nombre", account.ref2_nombre],
        ["Referencia 2 · Número de teléfono", account.ref2_tel || account.referencia_2],
        ["Referencia 3 · Nombre", account.ref3_nombre],
        ["Referencia 3 · Número de teléfono", account.ref3_tel],
        ["Referencia 3 · Parentesco", account.ref3_parentesco],
        ["Referencia 3 · Domicilio", account.ref3_domicilio],
      ],
    },
  ];

  accountDetails.replaceChildren();
  for (const group of groups) {
    const section = document.createElement("section");
    section.className = "account-detail-group";

    const heading = document.createElement("h3");
    heading.textContent = group.title;
    section.append(heading);

    const list = document.createElement("dl");
    for (const [label, value] of group.items) {
      const item = document.createElement("div");
      const term = document.createElement("dt");
      const description = document.createElement("dd");
      term.textContent = label;
      description.textContent = displayValue(value);
      item.append(term, description);
      list.append(item);
    }
    section.append(list);
    accountDetails.append(section);
  }
}

function renderAccountDetailsLegacy(account) {
  const groups = [
    {
      title: "Cuenta y crédito",
      items: [
        ["No. de crédito", account.numero_credito],
        ["Clave cliente", account.id_cuenta],
        ["Financiera", account.financiera?.nombre_financiera],
        ["Producto", account.producto],
        ["Estatus", account.estatus],
        ["Estatus MB", account.estatus_mb],
        ["Prioridad", account.prioridad],
        ["Campaña", account.campana || account.campanas],
        ["Fecha de asignación", displayDate(account.fecha_asig)],
        ["Gestiones acumuladas", account.gestiones],
      ],
    },
    {
      title: "Saldo y préstamo",
      items: [
        ["Monto original", displayMoney(account.capital)],
        ["Capital vigente", displayMoney(account.sdo_capital)],
        ["Capital vencido", displayMoney(account.capital_vencido)],
        ["Capital total", displayMoney(account.total)],
        ["Saldo al 06/07", displayMoney(account.sdo_actual)],
        ["Saldo vencido inicial", displayMoney(account.sdo_vencido_inicial)],
        ["Saldo vencido actual", displayMoney(account.saldo_vencido_actual)],
        ["Deudas vencidas Toku", displayMoney(account.deudas_vencidas_toku)],
        ["Intereses vencidos", displayMoney(account.intereses_vencidos)],
        ["Moratorios", displayMoney(account.moratorios)],
        ["Pagado en agosto", displayMoney(account.pagado_agosto)],
        ["Saldo estimado al 31/08", displayMoney(account.saldo_estimado_3108)],
        ["Proyección de cierre", displayMoney(account.proyeccion_cierre)],
      ],
    },
    {
      title: "Atraso y pagos",
      items: [
        ["Fecha de otorgamiento", displayDate(account.fecha_credito)],
        ["Último pago reportado", displayDate(account.fecha_ult_pago_finore)],
        ["Tiempo desde el último pago", daysSince(account.fecha_ult_pago_finore)],
        ["Días de atraso", account.mora_1],
        ["Días de atraso estimados", account.dias_atraso_estimado],
        ["Pagos atrasados (jun)", account.pagos_atrasados_jun],
        ["Pagos pendientes", account.pagos_ptes],
        ["Tramo", account.tramo],
        ["Frecuencia", account.frecuencia],
      ],
    },
    {
      title: "Seguimiento y promesa en Excel",
      items: [
        ["Última gestión del Excel", account.ult_gestion],
        ["Comentario del Excel", account.comentario],
        ["Estatus promesa actual", account.estatus_promesa_act],
        ["Estatus promesa anterior", account.estatus_promesa_ant],
        ["Fecha de promesa", displayDate(account.fecha_prom)],
        ["Monto prometido", displayMoney(account.monto_prom)],
        ["Asignación", account.asignacion],
        ["Agente indicado en Excel", account.agente_texto],
        ["Campañas", account.campanas],
        ["Campaña MB", account.campana],
        ["Rec MB", account.rec_mb],
        ["Marca interna", account.marca_interna],
      ],
    },
    {
      title: "Contacto y domicilio del titular",
      items: [
        ["Teléfono", account.celular],
        ["Domicilio completo", account.domicilio_completo],
        ["Calle", account.calle_numero],
        ["Colonia", account.colonia],
        ["Municipio", account.ciudad],
        ["Estado", account.estado],
        ["Código postal", account.codigo_postal],
      ],
    },
    {
      title: "Empresa y correo",
      items: [
        ["Empresa pagadora", account.empresa_pagadora],
        ["Teléfono de empresa", account.telempresa],
        ["Correo de empresa", account.correo_empresa],
        ["Estatus correo de empresa", account.estatus_correo_empresa],
        ["Correo del cliente", account.correo_cliente],
        ["Estatus correo del cliente", account.estatus_correo_cliente],
      ],
    },
    {
      title: "Referencia 1",
      note: "El layout no incluye domicilio para esta referencia.",
      items: [
        ["Nombre", account.ref1_nombre],
        ["Parentesco", account.ref1_parentesco],
        ["Teléfono", account.referencia_1],
        ["Tipo de teléfono", account.ref1_tipo_telefono],
        ["Domicilio", "No incluido en el layout"],
      ],
    },
    {
      title: "Referencia 2",
      note: "El layout no incluye domicilio para esta referencia.",
      items: [
        ["Nombre", account.ref2_nombre],
        ["Parentesco", account.ref2_parentesco],
        ["Teléfono", account.referencia_2],
        ["Tipo de teléfono", account.ref2_tipo_telefono],
        ["Dato adicional del Excel", account.en_predic],
        ["Domicilio", "No incluido en el layout"],
      ],
    },
    {
      title: "Pagos registrados en Excel",
      items: [
        ["Pagos (campo del Excel)", account.excel_pagos],
        ["Pagos de septiembre", displayMoney(account.pagos_sep)],
      ],
    },
  ];

  accountDetails.replaceChildren();
  for (const group of groups) {
    const section = document.createElement("section");
    section.className = "account-detail-group";

    const heading = document.createElement("h3");
    heading.textContent = group.title;
    section.append(heading);

    if (group.note) {
      const note = document.createElement("p");
      note.className = "account-detail-note";
      note.textContent = group.note;
      section.append(note);
    }

    const list = document.createElement("dl");
    for (const [label, value] of group.items) {
      const item = document.createElement("div");
      const term = document.createElement("dt");
      const description = document.createElement("dd");
      term.textContent = label;
      description.textContent = displayValue(value);
      item.append(term, description);
      list.append(item);
    }
    section.append(list);
    accountDetails.append(section);
  }
}

function setActiveNavigation(activeLink) {
  document.querySelectorAll(".nav-link").forEach((link) => {
    link.classList.toggle("active", link === activeLink);
  });
}

function showView(viewName) {
  if (!views[viewName]) {
    return;
  }

  Object.entries(views).forEach(([name, view]) => {
    view.hidden = name !== viewName;
  });
  document.querySelectorAll(".nav-link").forEach((link) => {
    link.classList.toggle("active", link.dataset.view === viewName);
  });
  breadcrumbView.textContent = viewLabels[viewName];

  if (viewName === "home") {
    loadDashboard();
  } else if (viewName === "portfolio" && !portfolioLoaded) {
    loadPortfolio();
  }
}

async function openCreditFromNbx() {
  if (!pendingCreditNumber) {
    return;
  }

  showView("management");
  managementSearchInput.value = pendingCreditNumber;
  managementSearchStatus.textContent = "Buscando el crédito recibido desde NBX…";
  managementAccountResults.replaceChildren();

  try {
    const params = new URLSearchParams({ numero_credito: pendingCreditNumber });
    const result = await getJson(
      `${API_URL}/api/carteras/por-numero-credito?${params}`,
    );

    if (!result.items.length) {
      managementSearchStatus.textContent =
        `No se encontró el crédito ${pendingCreditNumber} en la cartera.`;
      return;
    }

    if (result.items.length === 1) {
      managementSearchStatus.textContent = "Cuenta abierta desde NBX.";
      selectAccount(result.items[0]);
      return;
    }

    managementSearchStatus.textContent =
      `El crédito ${pendingCreditNumber} aparece en varias financieras. Selecciona la cuenta correcta.`;

    for (const account of result.items) {
      const option = document.createElement("button");
      option.className = "account-choice";
      option.type = "button";

      const name = document.createElement("strong");
      name.textContent = account.cliente || "Cliente sin nombre";
      const detail = document.createElement("span");
      detail.textContent = account.financiera?.nombre_financiera
        || "Financiera sin dato";
      option.append(name, detail);
      option.addEventListener("click", () => selectAccount(account));
      managementAccountResults.append(option);
    }
  } catch (error) {
    managementSearchStatus.textContent =
      `No se pudo abrir el crédito recibido desde NBX: ${error.message}`;
  }
}

async function searchAccountsForManagement(event) {
  event.preventDefault();
  const term = managementSearchInput.value.trim();

  if (!term) {
    managementSearchStatus.textContent = "Escribe un crédito, teléfono, nombre o apellido.";
    managementAccountResults.replaceChildren();
    return;
  }

  managementSearchStatus.textContent = "Buscando cuentas…";
  managementAccountResults.replaceChildren();

  try {
    const params = new URLSearchParams({ buscar: term, limite: "50", desde: "0" });
    const result = await getJson(`${API_URL}/api/carteras?${params}`);

    for (const account of result.items) {
      const option = document.createElement("button");
      option.className = "account-choice";
      option.type = "button";

      const name = document.createElement("strong");
      name.textContent = account.cliente || "Cliente sin nombre";
      const detail = document.createElement("span");
      detail.textContent = `Crédito ${account.numero_credito || "—"} · ${account.celular || account.casa || "Sin teléfono"}`;
      option.append(name, detail);
      option.addEventListener("click", () => selectAccount(account));
      managementAccountResults.append(option);
    }

    managementSearchStatus.textContent = result.items.length
      ? `Selecciona una cuenta. Se encontraron ${result.items.length}${result.hay_mas ? " o más" : ""}.`
      : "No se encontraron cuentas con esos datos.";
  } catch (error) {
    managementSearchStatus.textContent = error.message;
  }
}

function selectAccount(account) {
  selectedAccount = account;
  document.getElementById("management-account-id").value = account.id_cartera;
  document.getElementById("selected-account-title").textContent =
    account.cliente || "Cliente sin nombre";
  document.getElementById("selected-account-details").textContent =
    `Crédito ${account.numero_credito || "—"} · ${account.financiera?.nombre_financiera || "Financiera sin dato"} · Tel. ${account.celular || account.casa || "Sin teléfono"}`;
  renderAccountDetails(account);
  selectedAccountPanel.hidden = false;
  selectedAccountPanel.insertBefore(
    selectedAccountPanel.querySelector(".management-history"),
    document.getElementById("account-details"),
  );

  managementForm.reset();
  referenceForm.reset();
  referenceForm.hidden = true;
  document.getElementById("toggle-reference-form").hidden = Boolean(
    account.ref3_nombre || account.ref3_tel,
  );
  syncContactOptions(account);
  document.getElementById("management-account-id").value = account.id_cartera;
  promiseFields.hidden = true;
  document.getElementById("promise-date").required = false;
  document.getElementById("promise-amount").required = false;
  showView("management");
  loadManagementHistory();
}

function syncContactOptions(account) {
  const references = [
    ["Referencia 1", account.ref1_nombre, account.ref1_tel || account.referencia_1],
    ["Referencia 2", account.ref2_nombre, account.ref2_tel || account.referencia_2],
    ["Referencia 3", account.ref3_nombre, account.ref3_tel],
  ];
  const options = [
    new Option("Selecciona el contacto", ""),
    new Option("Titular", "titular"),
    new Option("No hubo contacto", "sin_contacto"),
  ];

  for (const [label, name, phone] of references) {
    if (!name && !phone) {
      continue;
    }
    const value = label.toLowerCase().replace(" ", "");
    const option = new Option(
      `${label}${name ? ` · ${name}` : ""}${phone ? ` · ${phone}` : ""}`,
      value,
    );
    options.push(option);
  }

  personContactedSelect.replaceChildren(...options);
}

function getContactPhone(contactValue) {
  if (!selectedAccount) {
    return null;
  }

  const phones = {
    titular: selectedAccount.celular || selectedAccount.casa,
    referencia1: selectedAccount.ref1_tel || selectedAccount.referencia_1,
    referencia2: selectedAccount.ref2_tel || selectedAccount.referencia_2,
    referencia3: selectedAccount.ref3_tel,
  };
  return phones[contactValue] || null;
}

function getContactName(contactValue) {
  if (!selectedAccount) {
    return "Sin contacto";
  }

  const names = {
    titular: "Titular",
    sin_contacto: "Sin contacto",
    referencia1: selectedAccount.ref1_nombre || "Referencia 1",
    referencia2: selectedAccount.ref2_nombre || "Referencia 2",
    referencia3: selectedAccount.ref3_nombre || "Referencia 3",
  };
  return names[contactValue] || "Otro contacto";
}

async function loadManagementHistory() {
  if (!selectedAccount) {
    return;
  }

  const status = document.getElementById("management-history-status");
  const resultFilter = document.getElementById("management-result-filter").value;
  managementHistoryList.replaceChildren();
  latestManagementSummary.hidden = true;
  status.textContent = "Cargando historial…";

  try {
    const params = new URLSearchParams({ limite: "20" });
    if (resultFilter) {
      params.set("codigo_resultado", resultFilter);
    }
    const result = await getJson(
      `${API_URL}/api/carteras/${selectedAccount.id_cartera}/gestiones?${params}`,
    );

    if (!result.items.length) {
      latestManagementSummary.hidden = true;
      status.textContent = "Esta cuenta todavía no tiene gestiones registradas.";
      return;
    }

    status.textContent = `Últimas ${result.items.length} gestiones`;
    const latest = result.items[0];
    document.getElementById("latest-management-result").textContent =
      RESULT_LABELS[latest.codigo_resultado]
      || latest.codigo_resultado
      || latest.estatus_contacto
      || "Gestión";
    document.getElementById("latest-management-date").textContent = latest.fecha_gestion
      ? new Date(latest.fecha_gestion).toLocaleString("es-MX")
      : "Fecha no disponible";
    document.getElementById("latest-management-comment").textContent =
      latest.comentario || "Sin comentario registrado.";
    latestManagementSummary.hidden = false;

    for (const management of result.items) {
      const item = document.createElement("article");
      const outcomeTone = ["no_contesto", "numero_incorrecto"].includes(
        management.codigo_resultado,
      )
        ? "unanswered"
        : management.codigo_resultado === "recado"
          && management.estatus_contacto === "tercero"
          ? "successful"
          : ["promesa", "pago_reportado"].includes(management.codigo_resultado)
            ? "successful"
            : "contacted";
      item.className = `history-item outcome-${outcomeTone}`;

      const heading = document.createElement("div");
      heading.className = "history-item-heading";
      const outcome = document.createElement("strong");
      outcome.textContent = RESULT_LABELS[management.codigo_resultado]
        || management.codigo_resultado
        || management.estatus_contacto
        || "Gestión";
      const date = document.createElement("time");
      date.textContent = management.fecha_gestion
        ? new Date(management.fecha_gestion).toLocaleString("es-MX")
        : "Fecha no disponible";
      heading.append(outcome, date);
      item.append(heading);

      if (management.persona_contactada || management.telefono_contactado) {
        const called = document.createElement("small");
        called.className = "history-contact-person";
        called.textContent = `Contacto: ${management.persona_contactada || "Sin nombre"}`
          + (management.telefono_contactado ? ` · ${management.telefono_contactado}` : "");
        item.append(called);
      }

      const comment = document.createElement("p");
      comment.textContent = management.comentario || "Sin comentario.";
      item.append(comment);

      if (management.fecha_promesa || management.monto_promesa) {
        const promise = document.createElement("small");
        const amount = management.monto_promesa
          ? ` · $${Number(management.monto_promesa).toLocaleString("es-MX", { minimumFractionDigits: 2 })}`
          : "";
        promise.textContent = `Promesa: ${management.fecha_promesa || "sin fecha"}${amount}`;
        item.append(promise);
      }

      managementHistoryList.append(item);
    }
  } catch (error) {
    status.textContent = `No se pudo cargar el historial: ${error.message}`;
  }
}
async function loadDashboard() {
  const status = document.getElementById("dashboard-status");

  try {
    const summary = await getJson(`${API_URL}/api/dashboard/general`);
    const total = Number(summary.cuentas_en_cartera || 0);
    const managed = Math.min(
      Number(summary.cuentas_con_gestion || 0),
      total,
    );
    const pending = Math.max(total - managed, 0);
    const progress = total ? Math.round((managed / total) * 100) : 0;

    document.getElementById("metric-accounts").textContent = total;
    const financialCounts = summary.cuentas_por_financiera || {};
    document.getElementById("metric-border-accounts").textContent =
      financialCounts["BORDER CREDIT"] || 0;
    document.getElementById("metric-finore-accounts").textContent =
      financialCounts.FINORE || 0;
    document.getElementById("metric-calls-yesterday").textContent =
      summary.llamadas_ayer || 0;
    document.getElementById("metric-calls-total").textContent =
      summary.llamadas_acumuladas || 0;
    document.getElementById("metric-gestions-today").textContent =
      summary.gestiones_hoy || 0;
    document.getElementById("metric-pending-followups").textContent =
      summary.gestiones_pendientes || 0;
    document.getElementById("metric-promises").textContent =
      summary.cuentas_promesadas || 0;
    document.getElementById("metric-refusals").textContent =
      summary.negativas_de_pago || 0;
    document.getElementById("metric-messages").textContent =
      summary.cuentas_con_recado || 0;
    document.getElementById("metric-payments").textContent =
      summary.pagos_reportados || 0;

    document.getElementById("portfolio-total").textContent = total;
    document.getElementById("portfolio-managed").textContent = managed;
    document.getElementById("portfolio-pending").textContent = pending;
    document.getElementById("portfolio-progress-label").textContent =
      `${progress}%`;
    document.getElementById("portfolio-progress-bar").style.width =
      `${progress}%`;
    await loadTodayManagements();
    status.textContent = "Métricas actualizadas desde Supabase";
  } catch (error) {
    status.textContent = `No se pudieron actualizar las métricas: ${error.message}`;
  }
}

async function loadTodayManagements() {
  const status = document.getElementById("today-management-status");
  const list = document.getElementById("today-management-list");
  const date = document.getElementById("today-management-date");
  status.textContent = "Cargando actividad…";
  list.replaceChildren();

  try {
    const result = await getJson(`${API_URL}/api/gestiones/hoy?limite=20`);
    date.textContent = new Date(`${result.fecha}T00:00:00`).toLocaleDateString(
      "es-MX",
      { weekday: "long", day: "numeric", month: "long", year: "numeric" },
    );

    if (!result.items.length) {
      status.textContent = "Todavía no hay gestiones registradas hoy.";
      return;
    }

    const groupedAccounts = new Map();
    for (const management of result.items) {
      const accountId = String(management.fk_cartera);
      const existing = groupedAccounts.get(accountId);
      if (existing) {
        existing.count += 1;
      } else {
        groupedAccounts.set(accountId, { management, count: 1 });
      }
    }

    status.textContent = `Actividad de ${groupedAccounts.size} cuenta(s) hoy`;
    for (const [accountId, group] of groupedAccounts) {
      const management = group.management;
      const item = document.createElement("article");
      item.className = "today-management-item";

      const heading = document.createElement("div");
      const customer = document.createElement("strong");
      customer.textContent = management.cuenta?.cliente || "Cliente sin nombre";
      const count = Number(result.conteos_por_cuenta?.[accountId] || group.count);
      const countLabel = document.createElement("span");
      countLabel.className = "today-management-count";
      countLabel.textContent = `${count} ${count === 1 ? "gestión" : "gestiones"} hoy`;
      heading.append(customer, countLabel);

      const detail = document.createElement("p");
      const time = management.fecha_gestion
        ? new Date(management.fecha_gestion).toLocaleTimeString("es-MX", {
          hour: "2-digit",
          minute: "2-digit",
        })
        : "Sin hora";
      detail.textContent = [
        RESULT_LABELS[management.codigo_resultado] || management.codigo_resultado,
        management.persona_contactada,
        management.cuenta?.numero_credito
          ? `Crédito ${management.cuenta.numero_credito}`
          : "",
        time,
      ].filter(Boolean).join(" · ");
      item.append(heading, detail);
      list.append(item);
    }
  } catch (error) {
    status.textContent = `No se pudo cargar la actividad: ${error.message}`;
  }
}
function updateSessionDuration() {
  if (!sessionStartedAt) {
    return;
  }

  const elapsedSeconds = Math.floor((Date.now() - sessionStartedAt) / 1000);
  const hours = String(Math.floor(elapsedSeconds / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((elapsedSeconds % 3600) / 60)).padStart(2, "0");
  const seconds = String(elapsedSeconds % 60).padStart(2, "0");
  document.getElementById("session-duration").textContent =
    `${hours}:${minutes}:${seconds}`;
}

async function loadPortfolio({ append = false } = {}) {
  portfolioList.hidden = false;

  if (!append) {
    portfolioOffset = 0;
    portfolioResults.replaceChildren();
    portfolioLoaded = false;
  }

  portfolioStatus.textContent = "Cargando cuentas desde Supabase…";
  portfolioLoadMoreButton.disabled = true;

  try {
    const params = new URLSearchParams({
      limite: String(PAGE_SIZE),
      desde: String(portfolioOffset),
    });
    const result = await getJson(`${API_URL}/api/carteras?${params}`);

    appendAccountRows(portfolioResults, result.items);
    portfolioOffset += result.items.length;
    portfolioLoaded = true;
    portfolioStatus.textContent = result.items.length
      ? `Se muestran ${portfolioOffset} cuenta(s) de la cartera general.`
      : "No hay más cuentas para mostrar.";
    portfolioLoadMoreButton.hidden = !result.hay_mas;
  } catch (error) {
    portfolioStatus.textContent = `No se pudo cargar la cartera: ${error.message}`;
    portfolioLoadMoreButton.hidden = true;
  } finally {
    portfolioLoadMoreButton.disabled = false;
  }
}

fileInput.addEventListener("change", () => {
  fileName.textContent = fileInput.files[0]?.name
    ?? "Ningún archivo seleccionado";
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!uploadForm.reportValidity()) {
    return;
  }

  const formData = new FormData();
  formData.append("fk_financiera", financialSelect.value);
  formData.append("file", fileInput.files[0]);

  importButton.disabled = true;
  importButton.textContent = "Importando...";
  importStatus.textContent = "Validando e importando las cuentas…";
  importStatus.classList.remove("upload-error", "upload-success");

  try {
    const result = await getJson(`${API_URL}/api/carteras/importar`, {
      method: "POST",
      body: formData,
    });

    importStatus.textContent = `${result.mensaje} ${result.registros_procesados} cuentas nuevas; se omitieron ${result.registros_omitidos} ya existentes para ${result.nombre_financiera}.`;
    importStatus.classList.add("upload-success");
    uploadForm.reset();
    fileName.textContent = "Ningún archivo seleccionado";

    await loadDashboard();
    if (!portfolioList.hidden || portfolioLoaded) {
      await loadPortfolio();
    }
  } catch (error) {
    importStatus.textContent = error.message;
    importStatus.classList.add("upload-error");
  } finally {
    importButton.disabled = false;
    importButton.textContent = "Importar cartera";
  }
});

portfolioButton.addEventListener("click", () => {
  loadPortfolio();
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginStatus.textContent = "Verificando acceso...";
  loginStatus.classList.remove("upload-error", "upload-success");

  try {
    await getJson(`${API_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: loginPassword.value }),
    });
  } catch (error) {
    loginStatus.textContent = error.message;
    loginStatus.classList.add("upload-error");
    return;
  }

  loginScreen.hidden = true;
  workspace.hidden = false;
  sessionStartedAt = Date.now();
  updateSessionDuration();
  loginPassword.value = "";
  loginStatus.textContent = "";
  showView(pendingCreditNumber ? "management" : "home");

  try {
    await loadFinancialOptions();
    await openCreditFromNbx();
  } catch (error) {
    financialSelect.replaceChildren(new Option("No disponibles", ""));
    importStatus.textContent = `${error.message} Confirma que FastAPI esté iniciado.`;
    importStatus.classList.add("upload-error");
  }
});

document.querySelectorAll(".nav-link").forEach((link) => {
  link.addEventListener("click", () => showView(link.dataset.view));
});

document.getElementById("top-register-management").addEventListener("click", () => {
  showView("management");
});

document.getElementById("back-to-home").addEventListener("click", () => {
  showView("home");
});

async function logout() {
  try {
    await getJson(`${API_URL}/api/auth/logout`, { method: "POST" });
  } catch (error) {
    // Se cierra la vista local aunque la sesión ya haya expirado.
  }

  workspace.hidden = true;
  loginScreen.hidden = false;
  sessionStartedAt = null;
  document.getElementById("session-duration").textContent = "00:00:00";
  loginForm.reset();
}

document.getElementById("logout-button").addEventListener("click", logout);
document.getElementById("top-logout-button").addEventListener("click", logout);

document.getElementById("report-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const status = document.getElementById("report-status");
  const button = document.getElementById("download-report");
  const params = new URLSearchParams();
  const startDate = document.getElementById("report-start-date").value;
  const endDate = document.getElementById("report-end-date").value;
  const result = document.getElementById("report-result").value;

  if (startDate) params.set("fecha_inicio", startDate);
  if (endDate) params.set("fecha_fin", endDate);
  if (result) params.set("codigo_resultado", result);

  button.disabled = true;
  status.textContent = "Preparando el archivo Excel…";
  try {
    const response = await fetch(
      `${API_URL}/api/reportes/gestiones.xlsx?${params}`,
    );
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "No se pudo crear el reporte.");
    }

    const workbook = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(workbook);
    link.download = "reporte_gestiones.xlsx";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    status.textContent = "Reporte descargado correctamente.";
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

document.querySelectorAll(".sidebar-brand, .login-brand .brand").forEach((brand) => {
  brand.addEventListener("click", (event) => {
    event.preventDefault();
    if (!workspace.hidden) {
      showView("home");
    }
  });
});

managementSearchForm.addEventListener("submit", searchAccountsForManagement);

document.getElementById("change-account").addEventListener("click", () => {
  selectedAccountPanel.hidden = true;
  managementSearchInput.focus();
});

callResultSelect.addEventListener("change", () => {
  const isPromise = callResultSelect.value === "promesa";
  const noContact = ["no_contesto", "numero_incorrecto"].includes(
    callResultSelect.value,
  );
  promiseFields.hidden = !isPromise;
  document.getElementById("promise-date").required = isPromise;
  document.getElementById("promise-amount").required = isPromise;
  if (noContact) {
    document.getElementById("contact-status").value = "sin_contacto";
    personContactedSelect.value = "sin_contacto";
  } else if (document.getElementById("contact-status").value === "sin_contacto") {
    document.getElementById("contact-status").value = "titular";
    personContactedSelect.value = "titular";
  }
});

personContactedSelect.addEventListener("change", () => {
  if (personContactedSelect.value === "sin_contacto") {
    document.getElementById("contact-status").value = "sin_contacto";
  } else if (personContactedSelect.value.startsWith("referencia")) {
    document.getElementById("contact-status").value = "tercero";
  } else if (personContactedSelect.value) {
    document.getElementById("contact-status").value = "titular";
  }
});

document.getElementById("management-result-filter").addEventListener(
  "change",
  loadManagementHistory,
);

document.getElementById("toggle-reference-form").addEventListener("click", () => {
  referenceForm.hidden = !referenceForm.hidden;
  if (!referenceForm.hidden) {
    document.getElementById("reference-name").focus();
  }
});

referenceForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedAccount || !referenceForm.reportValidity()) {
    return;
  }

  const status = document.getElementById("reference-status");
  const saveButton = document.getElementById("save-reference");
  saveButton.disabled = true;
  status.textContent = "Guardando referencia…";

  try {
    const result = await getJson(
      `${API_URL}/api/carteras/${selectedAccount.id_cartera}/referencias`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nombre: document.getElementById("reference-name").value.trim(),
          telefono: document.getElementById("reference-phone").value.trim(),
          parentesco: document.getElementById("reference-relationship").value.trim() || null,
          domicilio: document.getElementById("reference-address").value.trim() || null,
        }),
      },
    );
    selectedAccount = { ...selectedAccount, ...result.referencia };
    renderAccountDetails(selectedAccount);
    syncContactOptions(selectedAccount);
    referenceForm.reset();
    referenceForm.hidden = true;
    document.getElementById("toggle-reference-form").hidden = true;
    status.textContent = result.mensaje;
  } catch (error) {
    status.textContent = error.message;
  } finally {
    saveButton.disabled = false;
  }
});

managementForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!managementForm.reportValidity() || !selectedAccount) {
    return;
  }

  const resultCode = callResultSelect.value;
  const isPromise = resultCode === "promesa";
  const status = document.getElementById("management-submit-status");
  const saveButton = document.getElementById("save-management");
  const payload = {
    fk_cartera: selectedAccount.id_cartera,
    estatus_contacto: document.getElementById("contact-status").value,
    persona_contactada: getContactName(personContactedSelect.value),
    telefono_contactado: getContactPhone(personContactedSelect.value),
    codigo_resultado: resultCode,
    comentario: document.getElementById("management-comment").value.trim() || null,
    fecha_promesa: isPromise
      ? document.getElementById("promise-date").value
      : null,
    monto_promesa: isPromise
      ? Number(document.getElementById("promise-amount").value)
      : null,
  };

  saveButton.disabled = true;
  saveButton.textContent = "Guardando…";
  status.textContent = "Guardando la gestión…";
  status.classList.remove("upload-error", "upload-success");

  try {
    await getJson(`${API_URL}/api/gestiones`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    status.textContent = "La gestión quedó registrada.";
    status.classList.add("upload-success");
    const accountId = selectedAccount.id_cartera;
    managementForm.reset();
    document.getElementById("management-account-id").value = accountId;
    promiseFields.hidden = true;
    document.getElementById("promise-date").required = false;
    document.getElementById("promise-amount").required = false;

    await Promise.all([loadManagementHistory(), loadDashboard()]);
  } catch (error) {
    status.textContent = error.message;
    status.classList.add("upload-error");
  } finally {
    saveButton.disabled = false;
    saveButton.textContent = "Guardar gestión";
  }
});

portfolioLoadMoreButton.addEventListener("click", () => {
  loadPortfolio({ append: true });
});

document.getElementById("today-date").textContent = new Intl.DateTimeFormat(
  "es-MX",
  { day: "numeric", month: "short", year: "numeric" },
).format(new Date());

window.setInterval(updateSessionDuration, 1000);
window.setInterval(() => {
  if (!workspace.hidden) {
    loadDashboard();
  }
}, 60000);

loadFinancialOptions().catch((error) => {
  financialSelect.replaceChildren(new Option("No disponibles", ""));
  importStatus.textContent = `${error.message} Confirma que FastAPI esté iniciado.`;
  importStatus.classList.add("upload-error");
});

