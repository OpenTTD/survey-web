import jwt from '@tsndr/cloudflare-worker-jwt';
import * as public_keys from "./public_keys";

/*
 * This script handles two things:
 * - Accepting survey submissions and storing them in the R2 bucket.
 * - Generating new survey keys.
 *
 * The first URL always returns "200 OK" message, even when the
 * payload is invalid.
 * The second URL either returns a new survey-key, or returns
 * "404 Not Found" message.
 * Both are meant to make it a bit more difficult for people to
 * find valid keys, as you cannot tell if something went wrong
 * or what exactly went wrong.
 */

async function verifyResult(survey_key, env) {
    /* We first decode it, and later verify. This is because in the header should
     * be the ID of the key. But it also means we have to consider everything
     * untrusted till we verified it. */
    let jwt_payload;
    try {
        jwt_payload = await jwt.decode(survey_key);
    } catch {
        return "invalid";
    }

    /* Make sure it is a valid JWT header. */
    if (!jwt_payload || !jwt_payload.header) {
        return "invalid";
    }
    if (jwt_payload.header.type != "JWT" || jwt_payload.header.alg != "HS256" || !jwt_payload.header.kid || isNaN(jwt_payload.header.kid)) {
        return "invalid";
    }

    /* Check if we have a secret for the kid. */
    const kid = jwt_payload.header.kid;
    if (!env["JWT_SECRET_" + kid]) {
        return "invalid";
    }

    /* Verify the JWT. */
    const jwt_secret = env["JWT_SECRET_" + kid];
    const is_valid = await jwt.verify(survey_key, jwt_secret, { algorithms: ['HS256'] });
    return is_valid ? "verified" : "invalid";
}

/* Handle a single survey result; we do this after we send the
 * response to the user, as no matter what, they receive a "200 OK". */
async function handleSurveyResult(body, env) {
    try {
        const payload = JSON.parse(body);

        /* Check if the payload looks valid on the surface. */
        if (!("id" in payload) || !("key" in payload) || !("schema" in payload)) {
            return;
        }

        /* We only support schema 1 for now. */
        if (payload["schema"] != 1) {
            return;
        }

        /* Validate the UUID is a 32-character hexidecimal string. */
        const valid_uuid=/^([0-9A-F]{32})$/i;
        if (!valid_uuid.test(payload["id"])) {
            return;
        }

        /* Check if the key is verified. */
        const state = payload["key"] ? await verifyResult(payload["key"], env) : "unknown";

        /* Generate the object-name based on the current time, state, and the unique key; in the very
         * unlikely case there are two submissions that are identical, it is fine if they overwrite. */
        const date = (new Date()).toISOString().split("T", 2);
        const objectName = `${date[0]}/${date[1]}-${payload["id"]}.${state}.json`;

        /* Post the survey to the R2 bucket. */
        await env.SURVEY_BUCKET.put(objectName, body);
    } catch {
        /* What-ever goes wrong, act like nothing went wrong. This is to mitigate people trying to find an attack surface. */
    }
}

/* Handle verifying create request and the actual creating of a new survey-key. */
async function handleCreateSurveyKey(identifier, request, env) {
    try {
        const payload = await request.clone().json();
        const signature = request.headers.get("x-signature");

        /* Ensure the request is valid on the surface. */
        if (!identifier || !payload || !signature) {
            return new Response('Not Found', {
                status: 404,
            });
        }
        if (!(identifier in public_keys)) {
            return new Response('Not Found', {
                status: 404,
            });
        }

        /* Import the public key. */
        const public_key = await crypto.subtle.importKey(
            "spki",
            new Uint8Array(atob(public_keys[identifier]).split("").map(c => c.charCodeAt(0))),
            {
                name: "RSASSA-PKCS1-v1_5",
                hash: "SHA-256"
            },
            false,
            ["verify"]
        );

        /* Verify the signature is valid. */
        const result = await crypto.subtle.verify(
            "RSASSA-PKCS1-v1_5",
            public_key,
            new Uint8Array(atob(signature).split("").map(c => c.charCodeAt(0))),
            new TextEncoder().encode(await request.text())
        )

        if (!result) {
            return new Response('Not Found', {
                status: 404,
            });
        }

        /* Now we know the request is valid, create a new survey-key. */
        const kid = env.JWT_KID;
        const jwt_secret = env["JWT_SECRET_" + kid];
        const survey_key = await jwt.sign(payload, jwt_secret, { algorithm: "HS256", header: { type: "JWT", kid } });

        return new Response(survey_key);
    } catch {
        /* What-ever goes wrong, act like nothing went wrong. This is to mitigate people trying to find an attack surface. */
    }

    return new Response('Not Found', {
        status: 404,
    });
}

export default {
    async fetch(request, env, context) {
        if (request.method == 'POST') {
            const { pathname } = new URL(request.url);

            if (pathname == "/") {
                const payload = await request.text();
                context.waitUntil(handleSurveyResult(payload, env));
                return new Response("OK");
            } else if (pathname.startsWith("/create-survey-key/")) {
                const identifier = pathname.split("/")[2];
                return await handleCreateSurveyKey(identifier, request, env);
            } else {
                return new Response('Not Found', {
                    status: 404,
                });
            }
        } else {
            return new Response('Method Not Allowed', {
                status: 405,
                headers: {
                    Allow: 'POST',
                },
            });
        }
    }
}
