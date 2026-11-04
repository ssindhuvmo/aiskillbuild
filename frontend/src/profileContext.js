import { createContext } from "react";

// The signed-in user (name from Google) and their profile for the sidebar card. App loads both;
// Intake updates the profile on change.
export const ProfileContext = createContext({ user: null, profile: null, setProfile: () => {} });
