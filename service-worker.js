self.addEventListener("push", event => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (_) {}

  // iOS/iPadOS 18.4+ displays declarative Web Push directly.
  // Do not create a duplicate notification for that payload shape.
  if (payload?.web_push === 8030 && payload?.notification) return;

  const notification = payload?.notification && typeof payload.notification === "object"
    ? payload.notification
    : payload;
  const title = notification?.title || "Yartchives update is live";
  const targetUrl = notification?.navigate || notification?.data?.url || "./";
  const options = {
    body: notification?.body || "Your interactive change is deployed and ready to test.",
    tag: notification?.tag || "yartchives-deploy-live",
    requireInteraction: true,
    icon: "./assets/yartchives-hedgehog.png",
    data: { ...(notification?.data || {}), url: targetUrl },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const targetUrl = event.notification?.data?.url || "./";
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of windows) {
      if ("focus" in client) {
        await client.focus();
        if ("navigate" in client) await client.navigate(targetUrl);
        return;
      }
    }
    if (self.clients.openWindow) await self.clients.openWindow(targetUrl);
  })());
});
