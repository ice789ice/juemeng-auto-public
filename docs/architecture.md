# Architecture

Input script -> deterministic analyzer -> storyboard models -> human review -> local browser demo.

Original modules retained: config, drama parser, analysis context, skill loader, runtime budget, project bible, wardrobe state, production brief, asset matcher, review, storyboard schema/model/validator/postprocessing, mock and OpenAI analyzers. These are library modules; not all are connected to the small Flask demonstration.

The new Flask entry point uses an application factory and isolated in-memory state. The new browser adapter accepts an injected Playwright page and refuses destinations outside the local demonstration origin. No original platform adapter is included. Fictional text is authored for this candidate; no original production assets are distributed.

No skill prompt assets are copied. APIs that load director skills require caller-supplied files. Persistent asset editing, production submission and rendering are outside the runnable demo scope.
