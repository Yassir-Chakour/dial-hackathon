import { CONFIG } from 'src/global-config';

import { FranceUpdateView } from 'src/sections/france-update';

// ----------------------------------------------------------------------

export const metadata = { title: `France Update - ${CONFIG.appName}` };

export default function Page() {
  return <FranceUpdateView />;
}
