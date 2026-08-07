// The Digital Credentials call, with no page coupling. Open a session at the backend, hand its
// transports.dc offer to the wallet verbatim, forward the wallet's response back, return the
// verdict. A rejected promise (no wallet, user cancel, unsupported browser) propagates to the caller.
export async function present() {
  const session = await postJson("/av/session", {});
  const credential = await navigator.credentials.get(session.transports.dc);
  return postJson(`/av/response?session=${encodeURIComponent(session.session_id)}`, credential.data);
}

async function postJson(url, body) {
  const reply = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return reply.json();
}
