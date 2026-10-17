import { createContext } from "react";

// The signed-in user's profile for the sidebar card. App loads it; Intake updates it on change.
export const ProfileContext = createContext({ profile: null, setProfile: () => {} });
