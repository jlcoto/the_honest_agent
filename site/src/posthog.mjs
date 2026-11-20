// PostHog web analytics, shared by the landing page (layouts/Base.astro) and the docs
// (astro.config.mjs), both as an inline script in <head>.
// - EU Cloud, cookieless: nothing is stored in the visitor's browser, so no consent banner.
//   Needs "Enable cookieless tracking" on in the PostHog project, or the events are dropped.
// - Sent through PostHog's managed proxy on our own subdomain, so ad blockers don't drop them.
// - Only on the live site: local dev and Cloudflare preview deployments send nothing.
// The token is public by design: it can only send events, not read them.
const token = 'phc_qw3XW5sN9knGGw8hLU8MvsLRYJFjQCodL9Smph9CwFft';
const liveHosts = ['thehonestagent.dev', 'www.thehonestagent.dev'];

// The loader is PostHog's own snippet (posthog.com/docs/libraries/js), unchanged. It loads the
// SDK from the proxy's /static/ path, which serves PostHog's latest release.
const loader = `!function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],Object.defineProperty(u,"toString",{configurable:!0,enumerable:!0,writable:!0,value:function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e}}),Object.defineProperty(u.people,"toString",{configurable:!0,enumerable:!0,writable:!0,value:function(){return u.toString(1)+".people (stub)"}}),o="init capture register register_once register_for_session unregister unregister_for_session getFeatureFlag getFeatureFlagResult isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey getNextSurveyStep identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException loadToolbar get_property getSessionProperty createPersonProfile opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing debug".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);`;

const config = {
  api_host: 'https://m.thehonestagent.dev',
  ui_host: 'https://eu.posthog.com',
  defaults: '2026-08-30',
  cookieless_mode: 'always',
};

export const posthogSnippet = `if (${JSON.stringify(liveHosts)}.includes(location.hostname)) {
${loader}
posthog.init(${JSON.stringify(token)}, ${JSON.stringify(config)});
}`;
