// Everything the UI knows about the backend lives here. One place to change
// if the API moves, and the types mirror the Pydantic schemas exactly.

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export interface Product {
  id: number;
  name: string;
  price: string; // decimal string: money never round-trips through a float
  stock_quantity: number;
}

export interface CartItem {
  product_id: number;
  name: string;
  unit_price: string;
  quantity: number;
  line_total: string;
}

export interface Cart {
  id: string;
  items: CartItem[];
  total: string;
}

export interface OrderItem {
  product_id: number;
  name: string;
  quantity: number;
  price_at_purchase: string;
}

export interface Order {
  id: number;
  status: string;
  total: string;
  items: OrderItem[];
}

export interface OrderSummary {
  id: number;
  status: string;
  total: string;
  created_at: string;
}

export interface Recommendation {
  product_id: number;
  name: string;
  price: string;
  bought_together_count: number;
}

export interface ShoppingListItem {
  ingredient: string;
  product_id: number;
  name: string;
  price: string;
  in_stock: boolean;
}

export interface ShoppingList {
  dish: string;
  items: ShoppingListItem[];
  unavailable: string[];
  estimated_total: string;
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, body.detail ?? response.statusText);
  }
  return response.json() as Promise<T>;
}

export const api = {
  products: () => request<Product[]>("/products"),
  recommendations: (id: number) => request<Recommendation[]>(`/products/${id}/recommendations`),

  createCart: () => request<Cart>("/carts", { method: "POST" }),
  cart: (id: string) => request<Cart>(`/carts/${id}`),
  addItem: (id: string, productId: number, quantity: number) =>
    request<Cart>(`/carts/${id}/items`, {
      method: "POST",
      body: JSON.stringify({ product_id: productId, quantity }),
    }),
  setItemQuantity: (id: string, productId: number, quantity: number) =>
    request<Cart>(`/carts/${id}/items/${productId}`, {
      method: "PATCH",
      body: JSON.stringify({ quantity }),
    }),
  removeItem: (id: string, productId: number) =>
    request<Cart>(`/carts/${id}/items/${productId}`, { method: "DELETE" }),
  checkout: (id: string) => request<Order>(`/carts/${id}/checkout`, { method: "POST" }),

  orders: () => request<OrderSummary[]>("/orders"),
  order: (id: number) => request<Order>(`/orders/${id}`),

  dishes: () => request<string[]>("/assistant/dishes"),
  shoppingList: (dish: string) =>
    request<ShoppingList>(`/assistant/shopping-list?dish=${encodeURIComponent(dish)}`),
};

/**
 * One shopper, start to finish, on their own cart.
 *
 * Returns the HTTP status rather than throwing, because for the race demo a
 * 409 is a correct outcome and not an error -- it is the system refusing to
 * oversell.
 */
export async function raceCheckout(productId: number): Promise<number> {
  try {
    const cart = await api.createCart();
    await api.addItem(cart.id, productId, 1);
    await api.checkout(cart.id);
    return 201;
  } catch (error) {
    return error instanceof ApiError ? error.status : 0;
  }
}
