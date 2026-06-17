import { setupServer } from "msw/node";
import { handlers, m6Handlers } from "./handlers";

export const server = setupServer(...handlers, ...m6Handlers);
