import { useState } from "react";
import { raceCheckout, type Product } from "./api";

type Outcome = "pending" | "fulfilled" | "refused" | "limited" | "error";

const OUTCOME_BY_STATUS: Record<number, Outcome> = {
  201: "fulfilled",
  409: "refused",
  // Turned back by the rate limiter before reaching checkout. Neither a sale
  // nor a stock refusal, so it gets its own treatment rather than looking
  // like a failure.
  429: "limited",
};

interface Props {
  products: Product[];
  onFinished: () => void;
}

/**
 * Fires N checkouts at one product simultaneously and shows each landing.
 *
 * Promise.all means every request is genuinely in flight at once, so the
 * browser reproduces the same contention the pytest suite does -- against the
 * real API, not a simulation.
 */
export function RaceDemo({ products, onFinished }: Props) {
  const [productId, setProductId] = useState(products[0]?.id ?? 1);
  const [shoppers, setShoppers] = useState(10);
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [running, setRunning] = useState(false);
  const [startStock, setStartStock] = useState<number | null>(null);

  const product = products.find((p) => p.id === productId);

  async function run() {
    setRunning(true);
    setStartStock(product?.stock_quantity ?? null);
    setOutcomes(Array(shoppers).fill("pending"));

    await Promise.all(
      Array.from({ length: shoppers }, async (_, i) => {
        const status = await raceCheckout(productId);
        setOutcomes((prev) => {
          const next = [...prev];
          next[i] = OUTCOME_BY_STATUS[status] ?? "error";
          return next;
        });
      }),
    );

    setRunning(false);
    onFinished();
  }

  const fulfilled = outcomes.filter((o) => o === "fulfilled").length;
  const refused = outcomes.filter((o) => o === "refused").length;
  const limited = outcomes.filter((o) => o === "limited").length;
  const settled = outcomes.length > 0 && !running;
  const empty = (product?.stock_quantity ?? 0) === 0;

  return (
    <section className="panel hero">
      <h2>Send {shoppers} shoppers after the same item</h2>
      <p className="lede">
        Every request leaves at the same moment and competes for the same rows. Stock decides how
        many can win; the rest are turned away rather than sold something that isn't there.
      </p>

      <div className="race-controls">
        <label>
          Item
          <select
            value={productId}
            onChange={(e) => setProductId(Number(e.target.value))}
            disabled={running}
          >
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} — {p.stock_quantity} in stock
              </option>
            ))}
          </select>
        </label>

        <label>
          Shoppers
          <input
            type="number"
            min={1}
            max={40}
            value={shoppers}
            onChange={(e) => setShoppers(Math.min(40, Math.max(1, Number(e.target.value))))}
            disabled={running}
            className="race-shopper-count"
          />
        </label>

        <button type="button" onClick={run} disabled={running || !product || empty}>
          {running ? "Running…" : "Run the race"}
        </button>
      </div>

      {/* An empty shelf has nothing to contend for, and racing it is actively
          misleading: every shopper is refused when *adding* to the cart, so no
          checkout is ever sent and the panel would show 409s that the locking
          read never produced. Refuse the race rather than misreport it. */}
      {empty && !running && (
        <p className="verdict caution">
          {product?.name} is out of stock, so there is nothing to race for — every shopper would be
          turned away before checkout. Reset the shelf, or pick an item that still has stock.
        </p>
      )}

      {outcomes.length > 0 && (
        <>
          <div className="grid" aria-live="polite">
            {outcomes.map((outcome, i) => (
              <div key={i} className={`cell ${outcome}`}>
                {outcome === "fulfilled" && "201"}
                {outcome === "refused" && "409"}
                {outcome === "limited" && "429"}
                {outcome === "error" && "!"}
              </div>
            ))}
          </div>

          <div className="tally">
            <div className="fulfilled">
              <span className="n">{fulfilled}</span>fulfilled
            </div>
            <div className="refused">
              <span className="n">{refused}</span>turned away
            </div>
            {limited > 0 && (
              <div className="limited">
                <span className="n">{limited}</span>rate limited
              </div>
            )}
            <div>
              <span className="n">{product?.stock_quantity ?? "—"}</span>
              left {startStock !== null && `of ${startStock}`}
            </div>
          </div>
        </>
      )}

      {settled && limited > 0 && (
        <p className="verdict caution">
          {limited} of these never reached checkout — the rate limiter turned them
          back first, so no stock moved and this is not an overselling result.
          Wait a minute and run it again for a clean read.
        </p>
      )}

      {settled && limited === 0 && startStock !== null && (
        <p className="verdict">
          {fulfilled === Math.min(startStock, shoppers)
            ? `Exactly ${fulfilled} sold from ${startStock} in stock. Stock never went below zero, and no unit was sold twice.`
            : `${fulfilled} sold from ${startStock} in stock.`}
        </p>
      )}
    </section>
  );
}
