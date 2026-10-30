/** Own all side effects of a mounted research surface, including Strict Mode cleanup. */
export function researchRuntime(root: HTMLElement) {
  let disposed = false;
  const timers = new Set<number>(),
    intervals = new Set<number>(),
    frames = new Set<number>();
  const listeners: (() => void)[] = [];
  const lifetime = new AbortController();
  const observers: { disconnect(): void }[] = [];
  function listen(
    target: EventTarget,
    ...args: Parameters<EventTarget["addEventListener"]>
  ) {
    target.addEventListener(...args);
    listeners.push(() => target.removeEventListener(...args));
  }
  const documentProxy = new Proxy(document, {
    set(target, key, value) {
      return Reflect.set(target, key, value, target);
    },
    get(target, key) {
      if (key === "getElementById")
        return (id: string) => root.querySelector(`[id="${CSS.escape(id)}"]`);
      if (key === "querySelector")
        return (selector: string) =>
          selector.startsWith("meta[")
            ? target.head.querySelector(selector)
            : root.querySelector(selector);
      if (key === "querySelectorAll")
        return (selector: string) => root.querySelectorAll(selector);
      if (key === "addEventListener")
        return (...args: Parameters<EventTarget["addEventListener"]>) =>
          listen(target, ...args);
      const value = Reflect.get(target, key, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
  const windowProxy = new Proxy(window, {
    get(target, key) {
      if (key === "addEventListener")
        return (...args: Parameters<EventTarget["addEventListener"]>) =>
          listen(target, ...args);
      const value = Reflect.get(target, key, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
  return {
    document: documentProxy,
    window: windowProxy,
    signal: lifetime.signal,
    ResizeObserver: class extends globalThis.ResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        super(callback);
        observers.push(this);
      }
    },
    IntersectionObserver: class extends globalThis.IntersectionObserver {
      constructor(
        callback: IntersectionObserverCallback,
        options?: IntersectionObserverInit,
      ) {
        super(callback, options);
        observers.push(this);
      }
    },
    setTimeout(callback: (...args: any[]) => void, delay = 0, ...args: any[]) {
      if (disposed) return 0;
      const timer = window.setTimeout(() => {
        timers.delete(timer);
        if (!disposed) callback(...args);
      }, delay);
      timers.add(timer);
      return timer;
    },
    setInterval(callback: () => void, delay = 0) {
      if (disposed) return 0;
      const timer = window.setInterval(() => {
        if (!disposed) callback();
      }, delay);
      intervals.add(timer);
      return timer;
    },
    requestAnimationFrame(callback: FrameRequestCallback) {
      if (disposed) return 0;
      const frame = window.requestAnimationFrame((time) => {
        frames.delete(frame);
        if (!disposed) callback(time);
      });
      frames.add(frame);
      return frame;
    },
    dispose() {
      disposed = true;
      lifetime.abort();
      timers.forEach(clearTimeout);
      intervals.forEach(clearInterval);
      frames.forEach(cancelAnimationFrame);
      listeners.forEach((remove) => remove());
      observers.forEach((observer) => observer.disconnect());
    },
  };
}
