import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  type Cart,
  type OrderSummary,
  type Product,
  type Recommendation,
  type ShoppingList,
} from "./api";
import { RaceDemo } from "./RaceDemo";

const sar = (amount: string) => `SAR ${amount}`;

export default function App() {
  const [products, setProducts] = useState<Product[]>([]);
  const [cart, setCart] = useState<Cart | null>(null);
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [error, setError] = useState("");
  const previousStock = useRef<Record<number, number>>({});
  const [moved, setMoved] = useState<Set<number>>(new Set());

  const refresh = useCallback(async () => {
    const next = await api.products();
    const changed = new Set(
      next
        .filter((p) => previousStock.current[p.id] !== undefined)
        .filter((p) => previousStock.current[p.id] !== p.stock_quantity)
        .map((p) => p.id),
    );
    previousStock.current = Object.fromEntries(next.map((p) => [p.id, p.stock_quantity]));
    setProducts(next);
    setMoved(changed);
    setOrders(await api.orders());
  }, []);

  useEffect(() => {
    refresh().catch((e) => setError(String(e)));
  }, [refresh]);

  async function act<T>(work: () => Promise<T>) {
    setError("");
    try {
      return await work();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
      return undefined;
    }
  }

  async function add(productId: number) {
    const active = cart ?? (await api.createCart());
    const updated = await act(() => api.addItem(active.id, productId, 1));
    if (updated) setCart(updated);
  }

  async function placeOrder() {
    if (!cart) return;
    const order = await act(() => api.checkout(cart.id));
    if (order) {
      setCart(null);
      await refresh();
    }
  }

  return (
    <>
      <div className="strip">
        <span className="mark">SmartCart</span>
        <div className="chips">
          {products.map((p) => (
            <span
              key={p.id}
              className={`chip ${p.stock_quantity === 0 ? "depleted" : ""} ${
                moved.has(p.id) ? "moved" : ""
              }`}
            >
              {p.name.replace(/ \d.*$/, "")}
              <b>{p.stock_quantity}</b>
            </span>
          ))}
        </div>
      </div>

      <main>
        <h1>Nothing here can be sold twice.</h1>
        <p className="lede">
          A grocery service for Jeddah, built so that shoppers racing for the last item on the shelf
          get a truthful answer. Watch the counter above while the race runs.
        </p>

        {error && <p className="error">{error}</p>}

        {products.length > 0 && <RaceDemo products={products} onFinished={refresh} />}

        <div className="split">
          <Catalog products={products} onAdd={add} />
          <div>
            <CartPanel cart={cart} onCheckout={placeOrder} />
            <Assistant />
            <Orders orders={orders} />
          </div>
        </div>
      </main>
    </>
  );
}

function Catalog({ products, onAdd }: { products: Product[]; onAdd: (id: number) => void }) {
  const [suggestions, setSuggestions] = useState<Record<number, Recommendation[]>>({});

  // Bars are scaled against the fullest shelf in the shop, not against each
  // product's own peak. Per-product scaling would put every bar at 100% on
  // load, which says nothing; this shows at a glance which items are scarce --
  // and they still drain live as a race consumes stock.
  const fullest = Math.max(...products.map((p) => p.stock_quantity), 1);

  useEffect(() => {
    products.slice(0, 3).forEach(async (p) => {
      const recs = await api.recommendations(p.id).catch(() => []);
      if (recs.length) setSuggestions((s) => ({ ...s, [p.id]: recs }));
    });
  }, [products]);

  return (
    <section className="panel">
      <h2>Today's shelf</h2>
      <div className="shelf">
        {products.map((p) => {
          const remaining = p.stock_quantity / fullest;
          const soldOut = p.stock_quantity === 0;

          return (
            <article key={p.id} className={`card ${soldOut ? "sold-out" : ""}`}>
              <span className="name">{p.name}</span>

              <div className={`level ${remaining <= 0.25 ? "low" : ""}`}>
                <span style={{ width: `${Math.round(remaining * 100)}%` }} />
              </div>

              <span className="stock-note">
                {soldOut ? <span className="out">sold out</span> : `${p.stock_quantity} left`}
              </span>

              {suggestions[p.id] && (
                <p className="suggest">
                  Often with {suggestions[p.id].map((r) => r.name.replace(/ \d.*$/, "")).join(", ")}
                </p>
              )}

              <div className="card-foot">
                <span className="price">{sar(p.price)}</span>
                <button type="button" className="quiet" onClick={() => onAdd(p.id)} disabled={soldOut}>
                  Add
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function CartPanel({ cart, onCheckout }: { cart: Cart | null; onCheckout: () => void }) {
  return (
    <section className="panel">
      <h2>Your basket</h2>
      {!cart || cart.items.length === 0 ? (
        <p className="empty">Add something from the shelf to get started.</p>
      ) : (
        <>
          {cart.items.map((item) => (
            <div className="row" key={item.product_id}>
              <span className="name">{item.name}</span>
              <span className="meta">×{item.quantity}</span>
              <span className="price">{sar(item.line_total)}</span>
            </div>
          ))}
          <div className="total">
            <span>Total</span>
            <span>{sar(cart.total)}</span>
          </div>
          <button type="button" className="place-order" onClick={onCheckout}>
            Place order
          </button>
        </>
      )}
    </section>
  );
}

function Assistant() {
  const [dish, setDish] = useState("kabsa");
  const [list, setList] = useState<ShoppingList | null>(null);
  const [missing, setMissing] = useState("");

  async function look() {
    setMissing("");
    setList(null);
    try {
      setList(await api.shoppingList(dish));
    } catch (e) {
      setMissing(e instanceof ApiError ? e.detail : String(e));
    }
  }

  return (
    <section className="panel">
      <h2>Cooking something?</h2>
      <div className="race-controls">
        <input value={dish} onChange={(e) => setDish(e.target.value)} aria-label="Dish" />
        <button type="button" className="quiet" onClick={look}>
          Find ingredients
        </button>
      </div>

      {missing && <p className="error">{missing}</p>}

      {list && (
        <>
          {list.items.map((item) => (
            <div className="row" key={item.product_id}>
              <span className="name">{item.name}</span>
              <span className="meta">{item.ingredient}</span>
              <span className="price">{sar(item.price)}</span>
            </div>
          ))}
          <div className="total">
            <span>Estimated</span>
            <span>{sar(list.estimated_total)}</span>
          </div>
          {list.unavailable.length > 0 && (
            <p className="suggest unruled">
              We don't stock {list.unavailable.join(", ")} — you'll need those elsewhere.
            </p>
          )}
        </>
      )}
    </section>
  );
}

function Orders({ orders }: { orders: OrderSummary[] }) {
  return (
    <section className="panel">
      <h2>Past orders</h2>
      {orders.length === 0 ? (
        <p className="empty">No orders yet.</p>
      ) : (
        orders.slice(0, 6).map((o) => (
          <div className="row" key={o.id}>
            <span className="name">Order {o.id}</span>
            <span className="tag">{o.status}</span>
            <span className="price">{sar(o.total)}</span>
          </div>
        ))
      )}
    </section>
  );
}
