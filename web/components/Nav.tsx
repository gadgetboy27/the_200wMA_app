import Link from "next/link";
import type { Universe } from "@/types";

export default function Nav({ active }: { active: Universe }) {
  return (
    <div className="nav">
      <h1>200-WEEK MA SCAN</h1>
      <nav className="tabs">
        <Link className={active === "sp500" ? "tab on" : "tab"} href="/">
          S&amp;P 500
        </Link>
        <Link className={active === "crypto" ? "tab on" : "tab"} href="/crypto">
          Crypto
        </Link>
      </nav>
    </div>
  );
}
