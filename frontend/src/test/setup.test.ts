import { something } from "@/utils/nodeStyler";
import { readFileSync } from "fs";
import { resolve } from "path";
import { describe, it, expect } from "vitest";

describe("F0 setup", () => {
  it("T_F0_alias: @/ path alias resolves without error", () => {
    expect(something()).toBe("nodeStyler");
  });

  it("T_F0_tailwind: globals.css contains all three @tailwind directives", () => {
    const css = readFileSync(
      resolve(__dirname, "../assets/styles/globals.css"),
      "utf-8"
    );
    expect(css).toContain("@tailwind base");
    expect(css).toContain("@tailwind components");
    expect(css).toContain("@tailwind utilities");
  });
});
