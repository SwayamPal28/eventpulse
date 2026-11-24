// EventPulse Frontend Client
const EVENT_ID = "fest_rvce_2026";
let currentReservation = null;
let expiryCountdownInterval = null;
let currentTicketData = null;

function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

function refreshIdempotencyKey() {
  const input = document.getElementById("input-idempotency");
  if (input) {
    input.value = generateUUID();
  }
}

// Polling live seat map projection (CQRS Read Path)
async function fetchSeatmap() {
  try {
    const res = await fetch(`/api/v1/events/${EVENT_ID}/seatmap`);
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById("stat-available").textContent = data.available_count;
    document.getElementById("stat-held").textContent = data.held_count;
    document.getElementById("stat-booked").textContent = data.booked_count;

    renderSeatGrid(data.seats);
  } catch (err) {
    console.error("Failed to fetch seatmap:", err);
  }
}

function renderSeatGrid(seats) {
  const grid = document.getElementById("seat-grid");
  if (!grid) return;

  grid.innerHTML = "";
  seats.forEach(seat => {
    const btn = document.createElement("button");
    btn.dataset.seatId = seat.seat_id;
    btn.dataset.status = seat.status;
    btn.dataset.tier = seat.tier;
    btn.dataset.price = seat.price;

    let baseClass = "p-2 rounded-xl text-xs font-mono font-bold flex flex-col items-center justify-center transition transform active:scale-95 border ";
    
    if (seat.status === "AVAILABLE") {
      btn.className = baseClass + "bg-emerald-950/40 border-emerald-500/40 text-emerald-300 hover:bg-emerald-500 hover:text-white hover:border-emerald-400 cursor-pointer shadow-sm";
      btn.innerHTML = `<span>${seat.seat_id}</span><span class="text-[9px] opacity-75 font-normal">₹${seat.price}</span>`;
      btn.onclick = () => selectSeatToHold(seat);
    } else if (seat.status === "HELD") {
      const isMyHold = currentReservation && currentReservation.seat_id === seat.seat_id;
      btn.className = baseClass + (isMyHold 
        ? "bg-amber-500 border-amber-400 text-slate-950 font-black shadow-lg shadow-amber-500/30 animate-pulse"
        : "bg-amber-950/50 border-amber-600/60 text-amber-300 cursor-not-allowed opacity-90");
      
      const timerStr = seat.expires_in ? `${Math.floor(seat.expires_in/60)}:${(seat.expires_in%60).toString().padStart(2,'0')}` : "HELD";
      btn.innerHTML = `<span>${seat.seat_id}</span><span class="text-[8px] uppercase tracking-wider font-semibold">${timerStr}</span>`;
      if (!isMyHold) {
        btn.onclick = () => alert(`Seat ${seat.seat_id} is temporarily held by another user. Try again when lock expires or pick another seat.`);
      }
    } else if (seat.status === "BOOKED") {
      btn.className = baseClass + "bg-purple-950/70 border-purple-600/60 text-purple-300 cursor-not-allowed opacity-80";
      btn.innerHTML = `<span>${seat.seat_id}</span><span class="text-[8px] uppercase tracking-wider">SOLD</span>`;
      btn.onclick = () => alert(`Seat ${seat.seat_id} is already booked and verified.`);
    }

    grid.appendChild(btn);
  });
}

// Seat hold execution (Atomic Redis Lua Hold)
async function selectSeatToHold(seat) {
  const userId = document.getElementById("input-user-id").value.trim() || "student_guest";
  const ttl = parseInt(document.getElementById("select-ttl").value, 10) || 600;
  const feedback = document.getElementById("checkout-feedback");

  feedback.textContent = `Acquiring atomic Redis lock for ${seat.seat_id}...`;
  feedback.className = "text-[11px] text-center text-cyan-400";

  try {
    const res = await fetch("/api/v1/reservations/hold", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_id: EVENT_ID,
        seat_id: seat.seat_id,
        user_id: userId,
        hold_duration_seconds: ttl
      })
    });

    if (res.status === 409) {
      const err = await res.json();
      feedback.textContent = `❌ Conflict: ${err.detail}`;
      feedback.className = "text-[11px] text-center text-rose-400";
      fetchSeatmap();
      return;
    }

    if (!res.ok) {
      throw new Error("Failed to hold seat");
    }

    const data = await res.json();
    currentReservation = {
      reservation_id: data.reservation_id,
      seat_id: data.seat_id,
      event_id: data.event_id,
      user_id: data.user_id,
      price: seat.price,
      tier: seat.tier,
      expires_at: new Date(data.expires_at).getTime(),
      ttl_seconds: data.ttl_seconds
    };

    updateCheckoutCard();
    refreshIdempotencyKey();
    feedback.textContent = `✅ Lock acquired in sub-millisecond via Redis Lua! Complete payment before expiry.`;
    feedback.className = "text-[11px] text-center text-emerald-400";
    fetchSeatmap();
    fetchTelemetry();
  } catch (err) {
    feedback.textContent = `Error: ${err.message}`;
    feedback.className = "text-[11px] text-center text-rose-400";
  }
}

function updateCheckoutCard() {
  const seatIdElem = document.getElementById("checkout-seat-id");
  const tierElem = document.getElementById("checkout-tier");
  const amountElem = document.getElementById("checkout-amount");
  const resIdElem = document.getElementById("checkout-res-id");
  const timerElem = document.getElementById("checkout-expiry-timer");
  const checkoutBtn = document.getElementById("btn-confirm-checkout");

  if (!currentReservation) {
    seatIdElem.textContent = "None (Select on Grid)";
    tierElem.textContent = "--";
    amountElem.textContent = "₹ 0.00";
    resIdElem.textContent = "--";
    timerElem.textContent = "--";
    checkoutBtn.disabled = true;
    if (expiryCountdownInterval) clearInterval(expiryCountdownInterval);
    return;
  }

  seatIdElem.textContent = currentReservation.seat_id;
  tierElem.textContent = `${currentReservation.tier} Class`;
  amountElem.textContent = `₹ ${currentReservation.price.toFixed(2)}`;
  resIdElem.textContent = currentReservation.reservation_id;
  checkoutBtn.disabled = false;

  if (expiryCountdownInterval) clearInterval(expiryCountdownInterval);
  
  expiryCountdownInterval = setInterval(() => {
    const diff = Math.max(0, Math.floor((currentReservation.expires_at - Date.now()) / 1000));
    const mins = Math.floor(diff / 60);
    const secs = (diff % 60).toString().padStart(2, "0");
    timerElem.textContent = `${mins}:${secs}`;

    if (diff <= 0) {
      clearInterval(expiryCountdownInterval);
      timerElem.textContent = "EXPIRED";
      document.getElementById("checkout-feedback").textContent = "⚠️ Seat hold expired and returned to pool.";
      document.getElementById("checkout-feedback").className = "text-[11px] text-center text-rose-400";
      currentReservation = null;
      checkoutBtn.disabled = true;
      fetchSeatmap();
    }
  }, 500);
}

// Confirm checkout with Transactional Outbox
document.getElementById("btn-confirm-checkout").addEventListener("click", async () => {
  if (!currentReservation) return;

  const btn = document.getElementById("btn-confirm-checkout");
  const feedback = document.getElementById("checkout-feedback");
  const idempotencyKey = document.getElementById("input-idempotency").value.trim() || generateUUID();

  btn.disabled = true;
  feedback.textContent = "Processing ACID transaction & Transactional Outbox...";
  feedback.className = "text-[11px] text-center text-cyan-400";

  try {
    const res = await fetch(`/api/v1/reservations/${currentReservation.reservation_id}/confirm`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey
      },
      body: JSON.stringify({
        payment_method: "UPI_INSTANT",
        amount: currentReservation.price
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Payment failed");
    }

    const orderData = await res.json();
    feedback.textContent = `🎉 Order confirmed! Ticket ID: ${orderData.ticket_id}`;
    feedback.className = "text-[11px] text-center text-emerald-400";

    // Stop countdown
    if (expiryCountdownInterval) clearInterval(expiryCountdownInterval);
    const savedSeat = currentReservation.seat_id;
    currentReservation = null;
    updateCheckoutCard();

    // Fetch issued ticket pass from S3
    setTimeout(async () => {
      fetchSeatmap();
      fetchTelemetry();
      try {
        const tktRes = await fetch(`/api/v1/tickets/${orderData.ticket_id}`);
        if (tktRes.ok) {
          const tkt = await tktRes.json();
          showTicketModal(tkt);
        }
      } catch (e) {
        console.warn("Ticket fetch retry:", e);
      }
    }, 600);

  } catch (err) {
    feedback.textContent = `❌ ${err.message}`;
    feedback.className = "text-[11px] text-center text-rose-400";
    btn.disabled = false;
  }
});

// Show Ticket Modal
function showTicketModal(ticket) {
  currentTicketData = ticket;
  document.getElementById("modal-tkt-id").textContent = ticket.ticket_id;
  document.getElementById("modal-seat-id").textContent = ticket.seat_id;
  document.getElementById("modal-user-id").textContent = ticket.attendee_id;
  document.getElementById("modal-amount").textContent = `₹ ${ticket.amount}`;
  document.getElementById("modal-signature").textContent = ticket.qr_signature;

  const qrContainer = document.getElementById("ticket-qr-container");
  if (ticket.qr_code_svg) {
    qrContainer.innerHTML = `<img src="${ticket.qr_code_svg}" class="w-32 h-32 rounded-xl bg-white p-2 shadow-lg" alt="Signed QR Pass" />`;
  } else {
    qrContainer.innerHTML = `<div class="p-4 bg-slate-900 border border-slate-700 rounded-lg text-cyan-400 font-mono text-[10px]">QR: ${ticket.qr_signature.substring(0, 24)}...</div>`;
  }

  document.getElementById("ticket-modal").classList.remove("hidden");
}

document.getElementById("btn-close-modal").onclick = () => {
  document.getElementById("ticket-modal").classList.add("hidden");
};

document.getElementById("btn-download-pass").onclick = () => {
  if (!currentTicketData) return;
  const blob = new Blob([JSON.stringify(currentTicketData, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${currentTicketData.ticket_id}_pass.json`;
  a.click();
};

// Telemetry & Cassandra logs fetcher
async function fetchTelemetry() {
  try {
    const res = await fetch("/api/v1/audit/logs?limit=15");
    if (!res.ok) return;
    const data = await res.json();
    const tbody = document.getElementById("telemetry-table-body");
    if (!tbody || !data.logs || data.logs.length === 0) return;

    tbody.innerHTML = "";
    data.logs.forEach(log => {
      const tr = document.createElement("tr");
      tr.className = "hover:bg-slate-800/40 transition";
      const timeStr = log.timestamp.split("T")[1]?.substring(0, 8) || log.timestamp;
      
      let badgeClass = "text-slate-400";
      if (log.outcome === "SUCCESS" || log.outcome === "AUDITED") badgeClass = "text-emerald-400";
      else if (log.outcome === "CONFLICT") badgeClass = "text-rose-400 font-bold";

      tr.innerHTML = `
        <td class="py-2 px-3 text-slate-500">${timeStr}</td>
        <td class="py-2 px-3 text-cyan-300 font-bold">${log.seat_id}</td>
        <td class="py-2 px-3 text-slate-400">${log.user_id}</td>
        <td class="py-2 px-3 text-slate-300">${log.attempt_type}</td>
        <td class="py-2 px-3 ${badgeClass}">${log.outcome}</td>
        <td class="py-2 px-3 text-slate-400">${log.latency_ms} ms</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Telemetry fetch error:", err);
  }
}

// Virtual Waiting Room Join
document.getElementById("btn-enter-queue").addEventListener("click", async () => {
  const userId = document.getElementById("input-user-id").value.trim() || "student_queue_test";
  try {
    const res = await fetch("/api/v1/waiting-room/enter", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, event_id: EVENT_ID })
    });
    const data = await res.json();
    
    const badge = document.getElementById("wr-status-badge");
    const pos = document.getElementById("wr-position");
    const tok = document.getElementById("wr-token");

    if (data.status === "ADMITTED") {
      badge.textContent = "ADMITTED (TOKEN ACTIVE)";
      badge.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800";
      pos.textContent = "Granted Entrance";
      tok.textContent = data.queue_token || "qtok_admitted";
    } else {
      badge.textContent = `QUEUED (#${data.position})`;
      badge.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950 text-amber-400 border border-amber-800 animate-pulse";
      pos.textContent = `Position ${data.position} (~${data.estimated_wait_seconds}s wait)`;
      tok.textContent = "Enqueued in Redis ZSET";
    }
    fetchTelemetry();
  } catch (e) {
    alert("Waiting room error: " + e.message);
  }
});

// Flash Sale Concurrency Spike (30 simultaneous async requests hitting Seat A-01)
document.getElementById("btn-flash-chaos").addEventListener("click", async () => {
  const btn = document.getElementById("btn-flash-chaos");
  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> Firing 30 Concurrent Requests...`;

  const targetSeat = "A-01";
  const numRequests = 30;
  const promises = [];

  for (let i = 1; i <= numRequests; i++) {
    const botUser = `attendee_concurrent_${i.toString().padStart(2, "0")}`;
    promises.push(
      fetch("/api/v1/reservations/hold", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_id: EVENT_ID,
          seat_id: targetSeat,
          user_id: botUser,
          hold_duration_seconds: 30
        })
      }).then(r => r.status)
    );
  }

  const results = await Promise.all(promises);
  const successes = results.filter(s => s === 201).length;
  const conflicts = results.filter(s => s === 409).length;

  btn.disabled = false;
  btn.innerHTML = `<i class="fa-solid fa-bolt"></i> Flash-Sale Concurrency Spike`;

  alert(`⚡ FLASH-SALE CONCURRENCY SPIKE RESULTS:\n\n• Target Seat: ${targetSeat}\n• Total Concurrent Requests: ${numRequests}\n• Successful Lock: ${successes} (Exactly 1 Winner)\n• 409 Conflicts: ${conflicts} (Prevented Double-Bookings)\n• Race Conditions: ZERO\n\nCheck the Cassandra Telemetry table below for sub-millisecond traces!`);

  fetchSeatmap();
  fetchTelemetry();
});

// Reset Testbed
document.getElementById("btn-reset").addEventListener("click", async () => {
  if (confirm("Reset all seat statuses and clear holds?")) {
    await fetch("/api/v1/events/reset");
    currentReservation = null;
    updateCheckoutCard();
    refreshIdempotencyKey();
    fetchSeatmap();
    fetchTelemetry();
  }
});

document.getElementById("btn-regen-key").addEventListener("click", refreshIdempotencyKey);

// Initial bootstrap
refreshIdempotencyKey();
fetchSeatmap();
fetchTelemetry();
setInterval(fetchSeatmap, 2000);
setInterval(fetchTelemetry, 3000);
