import { useEffect, useState } from "react";
import type { Screen } from "./types";
import { getCurrentUser } from "./lib/auth";
import SignIn from "./screens/SignIn";
import TripList from "./screens/TripList";
import Chat from "./screens/Chat";

export default function App() {
  const [screen, setScreen] = useState<Screen>({ name: "signin" });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getCurrentUser().then((user) => {
      if (user) setScreen({ name: "trips" });
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="splash">
        <div className="splash-logo">✈</div>
      </div>
    );
  }

  if (screen.name === "signin") {
    return (
      <SignIn
        onSignedIn={() => setScreen({ name: "trips" })}
      />
    );
  }

  if (screen.name === "trips") {
    return (
      <TripList
        onOpenTrip={(tripId) => setScreen({ name: "chat", tripId })}
        onSignOut={() => setScreen({ name: "signin" })}
      />
    );
  }

  if (screen.name === "chat") {
    return (
      <Chat
        tripId={screen.tripId}
        onBack={() => setScreen({ name: "trips" })}
      />
    );
  }

  return null;
}
