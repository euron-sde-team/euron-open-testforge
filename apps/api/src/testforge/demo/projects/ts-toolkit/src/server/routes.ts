import { formatPrice } from "../money";

type Handler = (params: Record<string, string>) => { status: number; body: unknown };

/** A tiny method and path router (no dependencies). */
export class Router {
  private routes: { method: string; path: string; handler: Handler }[] = [];

  get(path: string, handler: Handler): void {
    this.routes.push({ method: "GET", path, handler });
  }

  post(path: string, handler: Handler): void {
    this.routes.push({ method: "POST", path, handler });
  }

  handle(method: string, path: string): { status: number; body: unknown } {
    const route = this.routes.find((r) => r.method === method && r.path === path);
    return route ? route.handler({}) : { status: 404, body: { error: "not found" } };
  }
}

export const router = new Router();

router.get("/health", () => ({ status: 200, body: { status: "ok" } }));
router.get("/prices/sample", () => ({ status: 200, body: { price: formatPrice(1999) } }));
