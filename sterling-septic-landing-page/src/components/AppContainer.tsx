import { type ReactNode } from 'react';

const AppContainer = ({ children }: { children: ReactNode }) => {
    return (
        <div className="max-w-5xl mx-auto">
            {children}
        </div>
    );
};

export default AppContainer;