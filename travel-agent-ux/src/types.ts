export type TripStatus = "planning" | "active" | "completed";
export type ItemType =
  | "flight"
  | "hotel"
  | "restaurant"
  | "event"
  | "activity"
  | "train"
  | "transfer";
export type Flexibility = "fixed" | "flexible" | "droppable";
export type WishlistStatus =
  | "wishlist"
  | "available"
  | "booked"
  | "unavailable"
  | "replaced";

export interface Destination {
  id: number;
  trip_id: number;
  city: string;
  country: string;
  country_code?: string;
  order: number;
  arrival_date?: string;
  departure_date?: string;
}

export interface Trip {
  id: number;
  user_id: number;
  title: string;
  status: TripStatus;
  budget_per_person?: number;
  currency: string;
  start_date?: string;
  end_date?: string;
  destinations: Destination[];
}

export interface ItineraryItem {
  id: number;
  itinerary_id: number;
  type: ItemType;
  flexibility: Flexibility;
  name: string;
  start_time?: string;
  end_time?: string;
  duration_mins?: number;
  location?: {
    lat?: number;
    lng?: number;
    address?: string;
    place_id?: string;
  };
  booking_ref?: string;
  booking_status?: string;
  confirmation_doc_url?: string;
  wallet_pass_url?: string;
  wishlist_status: WishlistStatus;
  item_data: Record<string, unknown>;
}

export interface ItineraryDay {
  id: number;
  trip_id: number;
  destination_id?: number;
  date: string;
  items: ItineraryItem[];
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
}

export interface Alert {
  id: number;
  trip_id: number;
  type: string;
  message: string;
  read_at?: string;
  created_at: string;
}

export type SSEEvent =
  | { type: "text"; content: string }
  | { type: "tool_use"; tool: string; id: string }
  | { type: "tool_result"; tool: string; result: unknown }
  | { type: "done" }
  | { type: "error"; message: string };

// App router state
export type Screen =
  | { name: "signin" }
  | { name: "trips" }
  | { name: "chat"; tripId: number };
