/**
 * Pre-render React Email templates to static HTML files.
 *
 * Usage:
 *   cd scripts/react-email-render
 *   npm install
 *   npm run render
 *
 * Output: ../../mock_gmail/seed/templates/html/*.html
 */

import { render } from "@react-email/render";
import { createElement as h } from "react";
import {
  Html, Head, Body, Container, Section, Row, Column, Text, Link,
  Img, Hr, Button, Preview, Heading, Font,
} from "@react-email/components";
import { writeFileSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(__dirname, "..", "..", "mock_gmail", "seed", "templates", "html");
mkdirSync(OUT_DIR, { recursive: true });

// ── Shared styles ──────────────────────────────────────────────

const base = {
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  backgroundColor: "#f6f6f6",
};

const container = { maxWidth: "600px", margin: "0 auto", backgroundColor: "#ffffff" };
const contentPad = { padding: "32px 40px" };
const footerStyle = { padding: "20px 40px", color: "#999", fontSize: "12px", lineHeight: "18px" };
const hrStyle = { borderColor: "#e6e6e6", margin: "20px 0" };
const smallMuted = { color: "#666", fontSize: "13px", lineHeight: "20px" };

// ── Template definitions ───────────────────────────────────────

const templates = {};

// --- GitHub: PR notification ---
templates["github-pr"] = () =>
  h(Html, null,
    h(Head, null),
    h(Preview, null, "{{sender_name}} opened a pull request"),
    h(Body, { style: base },
      h(Container, { style: container },
        h(Section, { style: { backgroundColor: "#24292e", padding: "16px 40px" } },
          h(Text, { style: { color: "#fff", fontSize: "16px", fontWeight: "bold", margin: 0 } }, "GitHub")
        ),
        h(Section, { style: contentPad },
          h(Text, { style: { fontSize: "14px", color: "#24292e", margin: "0 0 16px" } },
            h(Link, { href: "#", style: { color: "#0366d6", fontWeight: "bold" } }, "{{repo_name}}"),
            " #{{pr_number}}"
          ),
          h(Heading, { as: "h2", style: { fontSize: "20px", color: "#24292e", margin: "0 0 8px" } },
            "{{subject}}"
          ),
          h(Text, { style: smallMuted },
            "{{sender_name}} wants to merge {{branch_count}} commits into ",
            h("code", { style: { backgroundColor: "#f1f8ff", padding: "2px 6px", borderRadius: "3px", color: "#0366d6", fontSize: "12px" } }, "main"),
            " from ",
            h("code", { style: { backgroundColor: "#f1f8ff", padding: "2px 6px", borderRadius: "3px", color: "#0366d6", fontSize: "12px" } }, "{{branch_name}}")
          ),
          h(Hr, { style: hrStyle }),
          h(Text, { style: { fontSize: "14px", color: "#24292e", lineHeight: "22px" } },
            "{{body_preview}}"
          ),
          h(Section, { style: { textAlign: "center", marginTop: "24px" } },
            h(Button, { href: "#", style: { backgroundColor: "#2ea44f", color: "#fff", padding: "10px 24px", borderRadius: "6px", fontSize: "14px", fontWeight: "bold", textDecoration: "none" } },
              "View pull request"
            )
          )
        ),
        h(Section, { style: footerStyle },
          h(Text, { style: { margin: 0 } },
            "You are receiving this because you are subscribed to this repository."
          ),
          h(Text, { style: { margin: "4px 0 0" } },
            h(Link, { href: "#", style: { color: "#0366d6" } }, "Unsubscribe"),
            " from this thread."
          )
        )
      )
    )
  );

// --- Stripe: Receipt ---
templates["stripe-receipt"] = () =>
  h(Html, null,
    h(Head, null),
    h(Preview, null, "Receipt for {{amount}}"),
    h(Body, { style: base },
      h(Container, { style: container },
        h(Section, { style: { backgroundColor: "#635bff", padding: "24px 40px" } },
          h(Text, { style: { color: "#fff", fontSize: "20px", fontWeight: "bold", margin: 0 } }, "Stripe")
        ),
        h(Section, { style: contentPad },
          h(Heading, { as: "h2", style: { fontSize: "24px", color: "#1a1a1a", margin: "0 0 8px" } },
            "Receipt from {{merchant_name}}"
          ),
          h(Text, { style: smallMuted }, "Receipt #{{receipt_id}}"),
          h(Hr, { style: hrStyle }),
          h(Row, null,
            h(Column, { style: { width: "70%" } },
              h(Text, { style: { fontSize: "14px", color: "#1a1a1a", margin: "4px 0" } }, "{{item_description}}")
            ),
            h(Column, { style: { width: "30%", textAlign: "right" } },
              h(Text, { style: { fontSize: "14px", color: "#1a1a1a", margin: "4px 0" } }, "{{amount}}")
            )
          ),
          h(Hr, { style: hrStyle }),
          h(Row, null,
            h(Column, { style: { width: "70%" } },
              h(Text, { style: { fontSize: "16px", fontWeight: "bold", color: "#1a1a1a", margin: "4px 0" } }, "Total")
            ),
            h(Column, { style: { width: "30%", textAlign: "right" } },
              h(Text, { style: { fontSize: "16px", fontWeight: "bold", color: "#1a1a1a", margin: "4px 0" } }, "{{amount}}")
            )
          ),
          h(Text, { style: { ...smallMuted, marginTop: "24px" } },
            "Paid on {{date}} via card ending in {{card_last4}}"
          ),
          h(Section, { style: { textAlign: "center", marginTop: "24px" } },
            h(Button, { href: "#", style: { backgroundColor: "#635bff", color: "#fff", padding: "10px 24px", borderRadius: "6px", fontSize: "14px", fontWeight: "bold", textDecoration: "none" } },
              "View receipt"
            )
          )
        ),
        h(Section, { style: footerStyle },
          h(Text, { style: { margin: 0 } }, "Stripe, 354 Oyster Point Blvd, South San Francisco, CA 94080"),
        )
      )
    )
  );

// --- Google: Security alert ---
templates["google-security-alert"] = () =>
  h(Html, null,
    h(Head, null),
    h(Preview, null, "Security alert for your Google Account"),
    h(Body, { style: { ...base, backgroundColor: "#ffffff" } },
      h(Container, { style: { ...container, border: "1px solid #dadce0", borderRadius: "8px", overflow: "hidden" } },
        h(Section, { style: { padding: "24px 40px", textAlign: "center" } },
          h(Text, { style: { fontSize: "24px", color: "#202124", margin: "0 0 4px" } }, "Google")
        ),
        h(Section, { style: { padding: "0 40px 32px" } },
          h(Section, { style: { backgroundColor: "#fce8e6", borderRadius: "8px", padding: "16px 20px", marginBottom: "20px" } },
            h(Text, { style: { color: "#c5221f", fontSize: "14px", fontWeight: "bold", margin: "0 0 4px" } },
              "Critical security alert"
            ),
            h(Text, { style: { color: "#5f6368", fontSize: "13px", margin: 0 } },
              "{{alert_message}}"
            )
          ),
          h(Text, { style: { fontSize: "14px", color: "#202124", lineHeight: "22px" } },
            "A sign-in attempt was made from a device we didn't recognize."
          ),
          h(Section, { style: { backgroundColor: "#f8f9fa", borderRadius: "8px", padding: "16px 20px", marginTop: "16px" } },
            h(Text, { style: { fontSize: "13px", color: "#5f6368", margin: "4px 0" } }, "Device: {{device_name}}"),
            h(Text, { style: { fontSize: "13px", color: "#5f6368", margin: "4px 0" } }, "Location: {{location}}"),
            h(Text, { style: { fontSize: "13px", color: "#5f6368", margin: "4px 0" } }, "Time: {{time}}")
          ),
          h(Section, { style: { textAlign: "center", marginTop: "24px" } },
            h(Button, { href: "#", style: { backgroundColor: "#1a73e8", color: "#fff", padding: "10px 24px", borderRadius: "4px", fontSize: "14px", fontWeight: "500", textDecoration: "none" } },
              "Check activity"
            )
          )
        ),
        h(Section, { style: { ...footerStyle, textAlign: "center", borderTop: "1px solid #dadce0" } },
          h(Text, { style: { margin: 0 } },
            "This email was sent to {{user_email}} because Google takes your account security seriously."
          )
        )
      )
    )
  );

// --- Linear: Magic link ---
templates["linear-login"] = () =>
  h(Html, null,
    h(Head, null),
    h(Preview, null, "Your Linear login code"),
    h(Body, { style: base },
      h(Container, { style: container },
        h(Section, { style: { padding: "40px 40px 0" } },
          h(Text, { style: { fontSize: "18px", fontWeight: "bold", color: "#1a1a1a", margin: "0 0 24px" } }, "Linear")
        ),
        h(Section, { style: contentPad },
          h(Heading, { as: "h2", style: { fontSize: "20px", color: "#1a1a1a", margin: "0 0 16px" } },
            "Your login code"
          ),
          h(Section, { style: { backgroundColor: "#f5f5f5", borderRadius: "8px", padding: "20px", textAlign: "center", margin: "16px 0" } },
            h(Text, { style: { fontSize: "32px", fontWeight: "bold", letterSpacing: "6px", color: "#1a1a1a", margin: 0, fontFamily: "monospace" } },
              "{{login_code}}"
            )
          ),
          h(Text, { style: smallMuted },
            "This code expires in 10 minutes. If you didn't request this, you can safely ignore this email."
          )
        ),
        h(Section, { style: footerStyle },
          h(Text, { style: { margin: 0 } }, "Linear Inc, San Francisco, CA")
        )
      )
    )
  );

// --- Slack: Digest ---
templates["slack-digest"] = () =>
  h(Html, null,
    h(Head, null),
    h(Preview, null, "{{unread_count}} new messages in {{workspace_name}}"),
    h(Body, { style: base },
      h(Container, { style: container },
        h(Section, { style: { backgroundColor: "#4a154b", padding: "16px 40px" } },
          h(Text, { style: { color: "#fff", fontSize: "18px", fontWeight: "bold", margin: 0 } }, "Slack")
        ),
        h(Section, { style: contentPad },
          h(Heading, { as: "h2", style: { fontSize: "18px", color: "#1d1c1d", margin: "0 0 4px" } },
            "{{unread_count}} new messages"
          ),
          h(Text, { style: { ...smallMuted, marginBottom: "20px" } }, "in {{workspace_name}}"),
          h(Section, { style: { backgroundColor: "#f8f8f8", borderRadius: "8px", padding: "16px", borderLeft: "4px solid #4a154b" } },
            h(Text, { style: { fontSize: "13px", fontWeight: "bold", color: "#1d1c1d", margin: "0 0 4px" } }, "#{{channel_name}}"),
            h(Text, { style: { fontSize: "13px", color: "#616061", margin: 0 } }, "{{message_preview}}")
          ),
          h(Section, { style: { textAlign: "center", marginTop: "24px" } },
            h(Button, { href: "#", style: { backgroundColor: "#4a154b", color: "#fff", padding: "10px 24px", borderRadius: "4px", fontSize: "14px", fontWeight: "bold", textDecoration: "none" } },
              "Open Slack"
            )
          )
        ),
        h(Section, { style: footerStyle },
          h(Text, { style: { margin: 0 } }, "Slack Technologies, LLC  |  "),
          h(Link, { href: "#", style: { color: "#696969" } }, "Notification settings")
        )
      )
    )
  );

// --- Newsletter: Generic tech ---
templates["newsletter-tech"] = () =>
  h(Html, null,
    h(Head, null),
    h(Preview, null, "{{subject}}"),
    h(Body, { style: base },
      h(Container, { style: container },
        h(Section, { style: { padding: "32px 40px", borderBottom: "3px solid {{brand_color}}" } },
          h(Text, { style: { fontSize: "20px", fontWeight: "bold", color: "#1a1a1a", margin: 0 } }, "{{newsletter_name}}")
        ),
        h(Section, { style: contentPad },
          h(Heading, { as: "h1", style: { fontSize: "24px", color: "#1a1a1a", lineHeight: "32px", margin: "0 0 16px" } },
            "{{headline}}"
          ),
          h(Text, { style: { fontSize: "15px", color: "#333", lineHeight: "24px" } },
            "{{intro_paragraph}}"
          ),
          h(Hr, { style: hrStyle }),
          h(Text, { style: { fontSize: "14px", color: "#333", lineHeight: "22px" } },
            "{{body_content}}"
          ),
          h(Section, { style: { textAlign: "center", marginTop: "24px" } },
            h(Button, { href: "#", style: { backgroundColor: "{{brand_color}}", color: "#fff", padding: "10px 24px", borderRadius: "6px", fontSize: "14px", fontWeight: "bold", textDecoration: "none" } },
              "Read more"
            )
          )
        ),
        h(Section, { style: footerStyle },
          h(Text, { style: { margin: 0 } },
            "You received this email because you subscribed to {{newsletter_name}}. "
          ),
          h(Link, { href: "#", style: { color: "#696969" } }, "Unsubscribe")
        )
      )
    )
  );

// --- Datadog: Alert ---
templates["datadog-alert"] = () =>
  h(Html, null,
    h(Head, null),
    h(Preview, null, "[Alert] {{monitor_name}}"),
    h(Body, { style: base },
      h(Container, { style: container },
        h(Section, { style: { backgroundColor: "#632ca6", padding: "12px 40px" } },
          h(Text, { style: { color: "#fff", fontSize: "16px", fontWeight: "bold", margin: 0 } }, "Datadog")
        ),
        h(Section, { style: contentPad },
          h(Section, { style: { backgroundColor: "#fff3cd", border: "1px solid #ffc107", borderRadius: "4px", padding: "12px 16px", marginBottom: "16px" } },
            h(Text, { style: { fontSize: "14px", fontWeight: "bold", color: "#856404", margin: 0 } },
              "{{alert_status}} — {{monitor_name}}"
            )
          ),
          h(Text, { style: { fontSize: "14px", color: "#333", lineHeight: "22px" } },
            "{{alert_message}}"
          ),
          h(Section, { style: { backgroundColor: "#f8f9fa", borderRadius: "4px", padding: "12px 16px", marginTop: "16px", fontFamily: "monospace" } },
            h(Text, { style: { fontSize: "12px", color: "#495057", margin: "2px 0" } }, "Host: {{host}}"),
            h(Text, { style: { fontSize: "12px", color: "#495057", margin: "2px 0" } }, "Metric: {{metric}}"),
            h(Text, { style: { fontSize: "12px", color: "#495057", margin: "2px 0" } }, "Value: {{value}} (threshold: {{threshold}})")
          ),
          h(Section, { style: { textAlign: "center", marginTop: "24px" } },
            h(Button, { href: "#", style: { backgroundColor: "#632ca6", color: "#fff", padding: "10px 24px", borderRadius: "4px", fontSize: "14px", fontWeight: "bold", textDecoration: "none" } },
              "View monitor"
            )
          )
        ),
        h(Section, { style: footerStyle },
          h(Text, { style: { margin: 0 } }, "Datadog, Inc. 620 8th Ave, New York, NY 10018"),
        )
      )
    )
  );

// --- Luma: Event invite ---
templates["luma-event"] = () =>
  h(Html, null,
    h(Head, null),
    h(Preview, null, "You're invited: {{event_name}}"),
    h(Body, { style: base },
      h(Container, { style: container },
        h(Section, { style: { padding: "24px 40px" } },
          h(Text, { style: { fontSize: "16px", fontWeight: "bold", color: "#1a1a1a", margin: 0 } }, "luma")
        ),
        h(Section, { style: contentPad },
          h(Text, { style: { fontSize: "12px", textTransform: "uppercase", letterSpacing: "1px", color: "#999", margin: "0 0 8px" } }, "you're invited"),
          h(Heading, { as: "h1", style: { fontSize: "28px", color: "#1a1a1a", margin: "0 0 16px", lineHeight: "36px" } },
            "{{event_name}}"
          ),
          h(Section, { style: { backgroundColor: "#f7f7f7", borderRadius: "12px", padding: "20px", margin: "16px 0" } },
            h(Text, { style: { fontSize: "14px", color: "#333", margin: "4px 0" } }, "{{event_date}}"),
            h(Text, { style: { fontSize: "14px", color: "#333", margin: "4px 0" } }, "{{event_location}}"),
            h(Text, { style: { fontSize: "14px", color: "#666", margin: "4px 0" } }, "Hosted by {{host_name}}")
          ),
          h(Text, { style: { fontSize: "14px", color: "#333", lineHeight: "22px", marginTop: "16px" } },
            "{{event_description}}"
          ),
          h(Section, { style: { textAlign: "center", marginTop: "24px" } },
            h(Button, { href: "#", style: { backgroundColor: "#000", color: "#fff", padding: "12px 32px", borderRadius: "24px", fontSize: "14px", fontWeight: "bold", textDecoration: "none" } },
              "Register"
            )
          )
        ),
        h(Section, { style: footerStyle },
          h(Link, { href: "#", style: { color: "#696969" } }, "Manage notifications"),
          h(Text, { style: { margin: "4px 0 0" } }, "Luma HQ, San Francisco, CA")
        )
      )
    )
  );

// --- Mercury: Cash flow digest ---
templates["mercury-digest"] = () =>
  h(Html, null,
    h(Head, null),
    h(Preview, null, "Weekly cash flow digest: {{company_name}}"),
    h(Body, { style: base },
      h(Container, { style: container },
        h(Section, { style: { backgroundColor: "#1c1c1c", padding: "20px 40px" } },
          h(Text, { style: { color: "#fff", fontSize: "18px", fontWeight: "bold", margin: 0 } }, "Mercury")
        ),
        h(Section, { style: contentPad },
          h(Heading, { as: "h2", style: { fontSize: "20px", color: "#1a1a1a", margin: "0 0 4px" } },
            "Weekly cash flow digest"
          ),
          h(Text, { style: { ...smallMuted, marginBottom: "20px" } }, "{{company_name}} \u2022 {{date_range}}"),
          h(Section, { style: { backgroundColor: "#f8f9fa", borderRadius: "8px", padding: "20px" } },
            h(Row, null,
              h(Column, { style: { width: "33%" } },
                h(Text, { style: { fontSize: "11px", textTransform: "uppercase", color: "#999", margin: "0 0 4px" } }, "Balance"),
                h(Text, { style: { fontSize: "20px", fontWeight: "bold", color: "#1a1a1a", margin: 0 } }, "{{balance}}")
              ),
              h(Column, { style: { width: "33%" } },
                h(Text, { style: { fontSize: "11px", textTransform: "uppercase", color: "#999", margin: "0 0 4px" } }, "Income"),
                h(Text, { style: { fontSize: "20px", fontWeight: "bold", color: "#16a34a", margin: 0 } }, "+{{income}}")
              ),
              h(Column, { style: { width: "33%" } },
                h(Text, { style: { fontSize: "11px", textTransform: "uppercase", color: "#999", margin: "0 0 4px" } }, "Expenses"),
                h(Text, { style: { fontSize: "20px", fontWeight: "bold", color: "#dc2626", margin: 0 } }, "-{{expenses}}")
              )
            )
          ),
          h(Hr, { style: hrStyle }),
          h(Text, { style: { fontSize: "13px", fontWeight: "bold", color: "#1a1a1a", margin: "0 0 8px" } }, "Recent transactions"),
          h(Text, { style: { fontSize: "13px", color: "#666", margin: "4px 0" } }, "{{transaction_1}}"),
          h(Text, { style: { fontSize: "13px", color: "#666", margin: "4px 0" } }, "{{transaction_2}}"),
          h(Text, { style: { fontSize: "13px", color: "#666", margin: "4px 0" } }, "{{transaction_3}}"),
          h(Section, { style: { textAlign: "center", marginTop: "24px" } },
            h(Button, { href: "#", style: { backgroundColor: "#1c1c1c", color: "#fff", padding: "10px 24px", borderRadius: "6px", fontSize: "14px", fontWeight: "bold", textDecoration: "none" } },
              "View dashboard"
            )
          )
        ),
        h(Section, { style: footerStyle },
          h(Text, { style: { margin: 0 } }, "Mercury Technologies, Inc. | San Francisco, CA")
        )
      )
    )
  );

// --- PagerDuty: Incident ---
templates["pagerduty-incident"] = () =>
  h(Html, null,
    h(Head, null),
    h(Preview, null, "[Triggered] {{incident_title}}"),
    h(Body, { style: base },
      h(Container, { style: container },
        h(Section, { style: { backgroundColor: "#06ac38", padding: "12px 40px" } },
          h(Text, { style: { color: "#fff", fontSize: "16px", fontWeight: "bold", margin: 0 } }, "PagerDuty")
        ),
        h(Section, { style: contentPad },
          h(Section, { style: { backgroundColor: "#fef2f2", border: "1px solid #fecaca", borderRadius: "4px", padding: "12px 16px", marginBottom: "16px" } },
            h(Text, { style: { fontSize: "12px", textTransform: "uppercase", fontWeight: "bold", color: "#dc2626", margin: "0 0 4px" } },
              "{{severity}} severity incident triggered"
            ),
            h(Text, { style: { fontSize: "16px", fontWeight: "bold", color: "#1a1a1a", margin: 0 } },
              "{{incident_title}}"
            )
          ),
          h(Section, { style: { backgroundColor: "#f8f9fa", borderRadius: "4px", padding: "12px 16px" } },
            h(Text, { style: { fontSize: "12px", color: "#666", margin: "2px 0" } }, "Service: {{service_name}}"),
            h(Text, { style: { fontSize: "12px", color: "#666", margin: "2px 0" } }, "Escalation: {{escalation_policy}}"),
            h(Text, { style: { fontSize: "12px", color: "#666", margin: "2px 0" } }, "Triggered: {{triggered_at}}")
          ),
          h(Section, { style: { textAlign: "center", marginTop: "24px" } },
            h(Button, { href: "#", style: { backgroundColor: "#06ac38", color: "#fff", padding: "10px 24px", borderRadius: "4px", fontSize: "14px", fontWeight: "bold", textDecoration: "none", marginRight: "8px" } },
              "Acknowledge"
            ),
            h(Text, { style: { display: "inline", margin: "0 8px" } }, " "),
            h(Button, { href: "#", style: { backgroundColor: "#dc2626", color: "#fff", padding: "10px 24px", borderRadius: "4px", fontSize: "14px", fontWeight: "bold", textDecoration: "none" } },
              "Resolve"
            )
          )
        ),
        h(Section, { style: footerStyle },
          h(Text, { style: { margin: 0 } }, "PagerDuty, Inc."),
        )
      )
    )
  );

// --- Spam: Generic phishing ---
templates["spam-urgent"] = () =>
  h(Html, null,
    h(Head, null),
    h(Preview, null, "URGENT: {{subject}}"),
    h(Body, { style: { ...base, backgroundColor: "#ffffff" } },
      h(Container, { style: { ...container, border: "2px solid #ff0000" } },
        h(Section, { style: { ...contentPad, textAlign: "center" } },
          h(Heading, { as: "h1", style: { color: "#ff0000", fontSize: "28px" } },
            "{{headline}}"
          ),
          h(Text, { style: { fontSize: "16px", color: "#333", lineHeight: "24px" } },
            "{{body_text}}"
          ),
          h(Button, { href: "#", style: { backgroundColor: "#ff0000", color: "#fff", padding: "14px 40px", borderRadius: "4px", fontSize: "18px", fontWeight: "bold", textDecoration: "none", marginTop: "16px" } },
            "{{cta_text}}"
          ),
          h(Text, { style: { fontSize: "11px", color: "#999", marginTop: "20px" } },
            "If you did not request this, please click the button above immediately to secure your account."
          )
        )
      )
    )
  );

// ── Render all templates ───────────────────────────────────────

console.log("Rendering templates...\n");

for (const [name, factory] of Object.entries(templates)) {
  const element = factory();
  const html = await render(element, { pretty: true });
  const outPath = join(OUT_DIR, `${name}.html`);
  writeFileSync(outPath, html);
  console.log(`  ${name}.html (${(html.length / 1024).toFixed(1)} KB)`);
}

console.log(`\nDone! ${Object.keys(templates).length} templates written to ${OUT_DIR}`);
